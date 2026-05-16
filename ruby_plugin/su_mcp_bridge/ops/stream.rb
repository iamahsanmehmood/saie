require_relative '../logger'
require_relative 'win_capture'
require 'base64'

module SUMCPBridge
  module Ops
    # Stream — shared frame grabber for live-view consumers.
    #
    # Two consumers pull from this module:
    #   - view.snapshot (MCP tool)  → AI gets a fresh inline JPEG per call
    #   - StreamServer (HTTP MJPEG) → human watches via browser
    #
    # Two capture sources:
    #   - 'window' (default) → Win32 PrintWindow grab of the SketchUp main
    #                          window — INCLUDES axes, selection highlights,
    #                          tool overlays, inference, everything the user
    #                          actually sees. Native window resolution.
    #   - 'view'             → view.write_image() — clean OFFLINE render at
    #                          any size; no axes/selection/overlays. Useful
    #                          for high-resolution AI inspection of geometry.
    #
    # Both share an in-memory frame cache so back-to-back consumers don't
    # trigger redundant captures (each capture stalls the main thread).
    module Stream
      TEMP_PATH = File.join(
        ENV['TEMP'] || ENV['TMP'] || ENV['USERPROFILE'] || '.',
        'su_mcp_stream.jpg'
      ).freeze

      @last_frame = nil       # binary JPEG bytes
      @last_time  = 0.0       # seconds since epoch
      @width      = 800
      @height     = 600
      @quality    = 70        # JPEG quality 0-100
      @cache_ms   = 100       # reuse most-recent frame if newer than this
      @source     = 'window'  # default to full-fidelity window capture

      class << self
        attr_accessor :width, :height, :quality, :cache_ms, :source
        attr_reader   :last_time, :last_frame

        def configure(params)
          @width    = params['width'].to_i    if params['width']
          @height   = params['height'].to_i   if params['height']
          @quality  = params['quality'].to_i  if params['quality']
          @cache_ms = params['cache_ms'].to_i if params['cache_ms']
          @source   = params['source'].to_s   if params['source']
          @quality  = 1   if @quality < 1
          @quality  = 100 if @quality > 100
          @source   = 'window' unless %w[window view].include?(@source)
          status
        end

        def status
          {
            'width'    => @width,
            'height'   => @height,
            'quality'  => @quality,
            'cache_ms' => @cache_ms,
            'source'   => @source,
            'win_capture_available' => SUMCPBridge::WinCapture::AVAILABLE,
            'last_frame_bytes' => @last_frame ? @last_frame.bytesize : 0,
            'last_frame_age_ms' => @last_time > 0 ? ((Time.now.to_f - @last_time) * 1000).round : nil
          }
        end

        # Returns most recent JPEG bytes — captures fresh if cache is stale.
        # source override lets a single caller request a different capture
        # mode without disturbing the module's default.
        def grab_frame(force: false, source: nil)
          src = (source || @source).to_s
          src = 'view' if src == 'window' && !SUMCPBridge::WinCapture::AVAILABLE

          if !force && @last_frame
            age_ms = (Time.now.to_f - @last_time) * 1000
            return @last_frame if age_ms < @cache_ms
          end

          model = Sketchup.active_model
          return nil unless model

          begin
            if src == 'window'
              result = SUMCPBridge::WinCapture.capture_jpeg(TEMP_PATH)
              return nil unless result
            else
              model.active_view.write_image(
                filename:    TEMP_PATH,
                width:       @width,
                height:      @height,
                antialias:   false,
                compression: (@quality.to_f / 100.0),
                transparent: false
              )
            end
            @last_frame = File.binread(TEMP_PATH)
            @last_time  = Time.now.to_f
          rescue => e
            SUMCPBridge::Logger.warn("stream.grab[#{src}] failed: #{e.message}")
            return nil
          ensure
            File.delete(TEMP_PATH) rescue nil
          end

          @last_frame
        end

        # MCP op — returns inline base64 JPEG for AI consumption.
        # Per-call overrides (width/height/quality/source) trigger a fresh
        # capture, then restore the configured defaults.
        def snapshot(params)
          w = (params['width']  || @width).to_i
          h = (params['height'] || @height).to_i
          q = (params['quality'] || @quality).to_i
          src = (params['source'] || @source).to_s
          q = 1   if q < 1
          q = 100 if q > 100
          src = 'window' unless %w[window view].include?(src)

          # 'view' source honours requested dimensions; 'window' captures at
          # native window size (width/height are advisory).
          custom = (w != @width || h != @height || q != @quality || src != @source)
          force  = custom || params['force'] == true

          if custom
            saved = [@width, @height, @quality, @source]
            @width, @height, @quality, @source = w, h, q, src
          end

          data = grab_frame(force: force, source: src)

          if custom
            @width, @height, @quality, @source = *saved
          end

          return { 'error' => 'capture failed' } unless data

          {
            'image_base64' => Base64.strict_encode64(data),
            'mime'         => 'image/jpeg',
            'width'        => w,
            'height'       => h,
            'source'       => src,
            'bytes'        => data.bytesize,
            'timestamp'    => @last_time
          }
        end
      end
    end
  end
end
