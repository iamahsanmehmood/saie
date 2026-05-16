require 'socket'

module SUMCPBridge
  # StreamServer — tiny HTTP server for live MJPEG streaming of the SU view.
  #
  # Routes:
  #   GET /            → minimal HTML viewer page (auto-refreshing <img>)
  #   GET /stream      → multipart/x-mixed-replace JPEG stream (MJPEG)
  #   GET /snapshot.jpg → single fresh JPEG (one-shot)
  #   GET /healthz     → "ok" liveness probe
  #
  # The HTTP listener is opened immediately, but new connections are only
  # accepted and frames are only pushed while the timer is running
  # (start / stop control). Runs on the main thread via UI.start_timer,
  # so it shares the SketchUp event loop with the WebSocket transport.
  class StreamServer
    BOUNDARY = 'sumcpframe'.freeze
    DEFAULT_FPS = 5

    def initialize(start_port = 9877)
      @port = start_port
      open_server
      @clients   = []
      @timer_id  = nil
      @running   = false
      @target_fps = DEFAULT_FPS

      begin
        port_file = File.join(ENV['USERPROFILE'] || ENV['HOME'] || '.', '.su_mcp_stream_port')
        File.write(port_file, @port.to_s)
      rescue => e
        SUMCPBridge::Logger.warn("StreamServer: could not write port file: #{e.message}")
      end

      SUMCPBridge::Logger.info("StreamServer listening on http://localhost:#{@port}/")
    end

    attr_reader :port, :target_fps

    def running?;       @running;        end
    def client_count;   @clients.size;   end
    def tick_count;     @tick_count || 0; end
    def accept_count;   @accept_count || 0; end

    def url;        "http://localhost:#{@port}/"; end
    def stream_url; "http://localhost:#{@port}/stream"; end

    def start(fps: nil)
      @target_fps = fps.to_i if fps && fps.to_i > 0
      @target_fps = 1  if @target_fps < 1
      @target_fps = 30 if @target_fps > 30
      stop if @running
      interval = 1.0 / @target_fps
      @timer_id = UI.start_timer(interval, true) { tick }
      @running = true
      SUMCPBridge::Logger.info("StreamServer started at #{@target_fps} FPS")
    end

    def stop
      UI.stop_timer(@timer_id) if @timer_id
      @timer_id = nil
      @clients.each { |c| c[:socket].close rescue nil }
      @clients.clear
      @running = false
      SUMCPBridge::Logger.info("StreamServer stopped")
    end

    private

    def open_server
      attempts = 0
      begin
        @server = TCPServer.new('127.0.0.1', @port)
      rescue => e
        attempts += 1
        if attempts < 10
          @port += 1
          retry
        end
        raise "StreamServer: no port available near #{@port - attempts}"
      end
    end

    def tick
      @tick_count = (@tick_count || 0) + 1
      accept_pending
      push_to_clients
    rescue => e
      SUMCPBridge::Logger.warn("StreamServer.tick: #{e.message}")
    end

    def accept_pending
      loop do
        result = @server.accept_nonblock(exception: false)
        return if result.nil? || result == :wait_readable
        socket = result
        @accept_count = (@accept_count || 0) + 1
        begin
          handle_request(socket)
        rescue => e
          SUMCPBridge::Logger.warn("StreamServer: client error #{e.message}")
          socket.close rescue nil
        end
      end
    end

    # Read the request line + headers using non-blocking I/O with a short
    # timeout. The main thread cannot afford to block on socket.gets if the
    # client (or kernel) is slow to deliver bytes.
    def read_request_head(socket, timeout: 1.0)
      deadline = Time.now.to_f + timeout
      buf = ''.b
      until buf.include?("\r\n\r\n") || buf.include?("\n\n")
        remaining = deadline - Time.now.to_f
        return nil if remaining <= 0
        rs, _, _ = IO.select([socket], nil, nil, remaining)
        return nil unless rs && !rs.empty?
        begin
          chunk = socket.read_nonblock(4096, exception: false)
        rescue EOFError
          return nil
        end
        return nil if chunk == :wait_readable
        return nil if chunk.nil? || chunk.empty?
        buf << chunk.b
        return nil if buf.bytesize > 64 * 1024  # malformed / DoS guard
      end
      buf
    end

    def handle_request(socket)
      head = read_request_head(socket, timeout: 1.0)
      return socket.close unless head
      first_line = head.split(/\r?\n/, 2).first.to_s
      path = (first_line.split(/\s+/)[1] || '/').split('?').first

      case path
      when '/', '/index.html' then serve_viewer(socket)
      when '/stream', '/stream.mjpg' then serve_stream(socket)
      when '/snapshot.jpg', '/snapshot' then serve_snapshot(socket)
      when '/healthz' then respond(socket, 200, 'text/plain', 'ok')
      else respond(socket, 404, 'text/plain', 'Not Found')
      end
    end

    def serve_stream(socket)
      socket.write(
        "HTTP/1.1 200 OK\r\n" \
        "Content-Type: multipart/x-mixed-replace; boundary=#{BOUNDARY}\r\n" \
        "Cache-Control: no-cache, private\r\n" \
        "Pragma: no-cache\r\n" \
        "Connection: close\r\n" \
        "Access-Control-Allow-Origin: *\r\n\r\n"
      )
      @clients << { socket: socket, sent_at: 0 }
      SUMCPBridge::Logger.info("StreamServer: client joined (#{@clients.size} total)")
    end

    def serve_snapshot(socket)
      data = SUMCPBridge::Ops::Stream.grab_frame(force: true) || ''.b
      socket.write(
        "HTTP/1.1 200 OK\r\n" \
        "Content-Type: image/jpeg\r\n" \
        "Content-Length: #{data.bytesize}\r\n" \
        "Cache-Control: no-cache, private\r\n" \
        "Access-Control-Allow-Origin: *\r\n\r\n"
      )
      socket.write(data)
      socket.close rescue nil
    end

    def push_to_clients
      return if @clients.empty?
      data = SUMCPBridge::Ops::Stream.grab_frame
      return unless data
      header = "--#{BOUNDARY}\r\n" \
               "Content-Type: image/jpeg\r\n" \
               "Content-Length: #{data.bytesize}\r\n\r\n".b
      tail = "\r\n".b

      @clients.reject! do |c|
        begin
          c[:socket].write(header)
          c[:socket].write(data)
          c[:socket].write(tail)
          c[:sent_at] = Time.now.to_f
          false
        rescue
          c[:socket].close rescue nil
          SUMCPBridge::Logger.info("StreamServer: client left")
          true
        end
      end
    end

    def serve_viewer(socket)
      html = <<~HTML
        <!doctype html><html><head>
        <meta charset="utf-8">
        <title>SketchUp Live View</title>
        <style>
          html,body{margin:0;padding:0;background:#1a1a1a;color:#ddd;
            font-family:system-ui,Segoe UI,sans-serif;height:100%;overflow:hidden;}
          .wrap{display:flex;flex-direction:column;height:100vh;}
          header{padding:8px 14px;font-size:13px;background:#222;
            border-bottom:1px solid #333;display:flex;align-items:center;gap:12px;}
          .dot{width:8px;height:8px;border-radius:50%;background:#3a3;
            box-shadow:0 0 8px #3a3;animation:pulse 1.4s infinite;}
          @keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
          .meta{font-size:11px;color:#888;}
          .frame{flex:1;display:flex;align-items:center;justify-content:center;
            overflow:hidden;background:#000;}
          img{max-width:100%;max-height:100%;display:block;}
        </style></head><body>
        <div class="wrap">
          <header><span class="dot"></span>
            <strong>SketchUp Live View</strong>
            <span class="meta">port #{@port} · MJPEG · #{@target_fps} fps target</span>
          </header>
          <div class="frame"><img src="/stream" alt="SketchUp"></div>
        </div></body></html>
      HTML
      respond(socket, 200, 'text/html; charset=utf-8', html)
    end

    def respond(socket, code, ctype, body)
      reason = { 200 => 'OK', 404 => 'Not Found', 500 => 'Server Error' }[code] || 'OK'
      body_bytes = body.b
      socket.write(
        "HTTP/1.1 #{code} #{reason}\r\n" \
        "Content-Type: #{ctype}\r\n" \
        "Content-Length: #{body_bytes.bytesize}\r\n" \
        "Access-Control-Allow-Origin: *\r\n" \
        "Cache-Control: no-cache, private\r\n\r\n"
      )
      socket.write(body_bytes)
      socket.close rescue nil
    end
  end
end
