require 'fiddle'
require 'fiddle/import'
require_relative '../logger'

module SUMCPBridge
  # WinCapture — screen-pixel capture of the SketchUp main window.
  #
  # Capture pipeline (source: 'window'):
  #   1. Find SketchUp's HWND by enumerating windows owned by our PID
  #      (Process.pid == SketchUp process — Ruby runs inside it).
  #   2. GetWindowRect → screen coordinates of the SketchUp window.
  #   3. GetDC(nil) → screen device context (captures live pixels from display).
  #   4. BitBlt from screen at [left, top, width, height] → memory DC.
  #   5. GetDIBits → raw BGR pixel buffer.
  #   6. Write BMP → Sketchup::ImageRep.load → save as JPEG.
  #
  # WHY GetWindowDC + BitBlt instead of PrintWindow or GetDC(nil):
  #
  #   PrintWindow(hwnd, dc, PW_RENDERFULLCONTENT) forces SketchUp to do a new
  #   offline repaint. SketchUp's axes, selection highlights, and gizmos are
  #   drawn into the LIVE framebuffer during interactive rendering — they are
  #   NOT reproduced during a forced WM_PRINT repaint. Result: clean geometry
  #   but missing all interactive overlays.
  #
  #   GetDC(nil) + BitBlt reads live screen pixels at SketchUp's position.
  #   Correct pixels — but captures whatever window is on top. If the user has
  #   Chrome in front (watching the stream), it captures Chrome, not SketchUp.
  #
  #   GetWindowDC(hwnd) + BitBlt reads from SketchUp's OWN window DC — the
  #   last frame the GPU composited into SketchUp's off-screen surface. This
  #   is the existing rendered content, NOT a new render, so ALL overlays that
  #   SketchUp drew during its last interactive paint are present: axes ✓,
  #   blue selection outline ✓, orbit gizmo ✓, tool feedback ✓.
  #   Works even when SketchUp is behind Chrome or any other window.
  #
  # Windows-only — uses user32.dll + gdi32.dll via Fiddle.
  module WinCapture
    extend Fiddle::Importer

    DIB_RGB_COLORS = 0
    BI_RGB         = 0
    SRCCOPY        = 0x00CC0020

    begin
      dlload 'user32.dll', 'gdi32.dll'

      typealias 'HWND',    'void*'
      typealias 'HDC',     'void*'
      typealias 'HBITMAP', 'void*'
      typealias 'HGDIOBJ', 'void*'
      typealias 'BOOL',    'int'
      typealias 'UINT',    'unsigned int'
      typealias 'DWORD',   'unsigned long'
      typealias 'LPRECT',  'void*'
      typealias 'LPCWSTR', 'void*'
      typealias 'LPVOID',  'void*'

      extern 'BOOL  GetWindowRect(HWND, LPRECT)'
      # GetWindowDC(hwnd) returns the window's OWN DC — reads the last
      # composited frame including all OpenGL overlays (axes, selection, etc.)
      # without forcing a new render and without needing the window in front.
      extern 'HDC   GetWindowDC(HWND)'
      extern 'int   ReleaseDC(HWND, HDC)'
      extern 'HDC   CreateCompatibleDC(HDC)'
      extern 'HBITMAP CreateCompatibleBitmap(HDC, int, int)'
      extern 'HGDIOBJ SelectObject(HDC, HGDIOBJ)'
      extern 'BOOL  DeleteObject(HGDIOBJ)'
      extern 'BOOL  DeleteDC(HDC)'
      extern 'int   GetDIBits(HDC, HBITMAP, UINT, UINT, LPVOID, LPVOID, UINT)'
      extern 'BOOL  BitBlt(HDC, int, int, int, int, HDC, int, int, DWORD)'

      # PID-based window enumeration — all in user32.dll
      extern 'DWORD GetWindowThreadProcessId(HWND, LPVOID)'
      extern 'HWND  FindWindowExW(HWND, HWND, LPCWSTR, LPCWSTR)'
      extern 'BOOL  IsWindowVisible(HWND)'
      extern 'int   GetWindowTextW(HWND, LPVOID, int)'

      AVAILABLE = true
    rescue => e
      AVAILABLE = false
      DLL_LOAD_ERROR = e.message
    end

    class << self
      # Find the SketchUp main window by enumerating all top-level windows
      # belonging to our process (Process.pid == SketchUp's PID).
      # Picks the largest visible window with a non-empty title.
      def find_sketchup_window
        return nil unless AVAILABLE

        our_pid   = Process.pid
        best_hwnd = nil
        best_area = 0

        hwnd = FindWindowExW(nil, nil, nil, nil)
        while hwnd && hwnd.to_i != 0
          pid_buf = "\x00\x00\x00\x00".b
          GetWindowThreadProcessId(hwnd, pid_buf)
          pid = pid_buf.unpack1('L')

          if pid == our_pid && IsWindowVisible(hwnd) != 0
            title_buf = "\x00".b * 512
            tlen = GetWindowTextW(hwnd, title_buf, 256)
            if tlen > 0
              rect = [0, 0, 0, 0].pack('l4')
              if GetWindowRect(hwnd, rect) != 0
                l, t, r, b = rect.unpack('l4')
                area = (r - l) * (b - t)
                if area > best_area
                  best_area = area
                  best_hwnd = hwnd.to_i
                end
              end
            end
          end

          hwnd = FindWindowExW(nil, hwnd, nil, nil)
        end

        best_hwnd
      end

      # Capture from the SCREEN at SketchUp's window position.
      # Returns [bgr_bytes, width, height, row_bytes] or nil on failure.
      #
      # GetDC(nil) gives the desktop (screen) DC — its pixels are exactly
      # what the GPU sent to the monitor, including all OpenGL overlays.
      def capture_raw(hwnd = nil)
        return nil unless AVAILABLE
        hwnd ||= find_sketchup_window
        return nil if hwnd.nil? || hwnd == 0

        rect = [0, 0, 0, 0].pack('l4')
        return nil if GetWindowRect(hwnd, rect) == 0
        left, top, right, bottom = rect.unpack('l4')
        width  = right  - left
        height = bottom - top
        return nil if width <= 0 || height <= 0

        # Read from SketchUp's OWN window DC — the last frame it rendered.
        # This is the existing composited content: axes, selection, gizmos all
        # present. Works even when SketchUp is behind Chrome or other windows.
        win_dc = GetWindowDC(hwnd)
        return nil if win_dc.nil? || win_dc.to_i == 0

        mem_dc = CreateCompatibleDC(win_dc)
        bmp    = CreateCompatibleBitmap(win_dc, width, height)
        old    = SelectObject(mem_dc, bmp)

        # BitBlt from the window's DC (offset 0,0 = top-left of the window)
        BitBlt(mem_dc, 0, 0, width, height, win_dc, 0, 0, SRCCOPY)

        # BITMAPINFOHEADER — negative height = top-down DIB
        bih = [40, width, -height, 1, 24, BI_RGB, 0, 0, 0, 0, 0]
                .pack('LllSSLLllLL')
        row_bytes = ((width * 3 + 3) / 4) * 4
        buf = "\0".b * (row_bytes * height)

        GetDIBits(mem_dc, bmp, 0, height, buf, bih, DIB_RGB_COLORS)

        SelectObject(mem_dc, old)
        DeleteObject(bmp)
        DeleteDC(mem_dc)
        ReleaseDC(hwnd, win_dc)

        [buf, width, height, row_bytes]
      rescue => e
        SUMCPBridge::Logger.warn("WinCapture.capture_raw failed: #{e.message}") rescue nil
        nil
      end

      # Write a raw BGR buffer as a 24-bit Windows BMP file.
      def write_bmp(bgr, width, height, _row_bytes, path)
        pixels    = bgr.bytesize
        file_size = 14 + 40 + pixels
        fh = "BM".b + [file_size, 0, 0, 54].pack('Lssl')
        ih = [40, width, -height, 1, 24, BI_RGB, pixels, 2835, 2835, 0, 0]
                .pack('LllSSLLllLL')
        File.binwrite(path, fh + ih + bgr)
      end

      # Capture the SketchUp window and save as JPEG at jpeg_path.
      # Returns [width, height] on success, nil on failure.
      def capture_jpeg(jpeg_path)
        return nil unless AVAILABLE
        raw = capture_raw
        return nil unless raw
        bgr, w, h, row_bytes = raw

        bmp_path = jpeg_path.sub(/\.[^.]+\z/, '') + '.tmp.bmp'
        write_bmp(bgr, w, h, row_bytes, bmp_path)

        rep = Sketchup::ImageRep.new(bmp_path)
        rep.save_file(jpeg_path)
        File.delete(bmp_path) rescue nil

        [w, h]
      rescue => e
        SUMCPBridge::Logger.warn("WinCapture.capture_jpeg failed: #{e.message}") rescue nil
        nil
      end
    end
  end
end
