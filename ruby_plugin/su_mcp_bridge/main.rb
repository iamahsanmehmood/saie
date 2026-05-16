require 'json'
require_relative 'config'
require_relative 'logger'
require_relative 'envelope'
require_relative 'transport'
require_relative 'stream_server'
require_relative 'ai_id'
require_relative 'ops/wall'
require_relative 'ops/opening'
require_relative 'ops/capture'
require_relative 'ops/win_capture'
require_relative 'ops/stream'
require_relative 'ops/view_control'
require_relative 'ops/slab'
require_relative 'ops/primitive'
require_relative 'ops/query'
require_relative 'ops/dimension'
require_relative 'ops/roof'
require_relative 'ops/component'
require_relative 'ops/material'
require_relative 'ops/lifecycle'
require_relative 'ops/clash'
require_relative 'ops/animation'
require_relative 'ops/attr'
require_relative 'ops/execute'

module SUMCPBridge
  PLUGIN_VERSION  = '1.0.0'
  PROTOCOL_VERSION = '1.0'

  class Server
    attr_reader :port

    def initialize(port = nil)
      # Resolution order (most → least specific):
      #   1. explicit `port` argument
      #   2. per-user override saved via "Configure Port..." menu
      #   3. saie.toml [bridge].port (or SAIE_BRIDGE_PORT env var)
      #   4. hardcoded 9876
      config_port = SUMCPBridge::Config.bridge[:port] rescue 9876
      saved_port  = Sketchup.read_default("SU_MCP_Bridge", "port", config_port)
      @port = port || saved_port
      @transport = WSTransport.new(@port)
      @port = @transport.port
      @timer_id  = nil
      @stream_server = nil   # lazy — created on first stream operation
      @handlers  = build_handlers
    end

    # Lazy-init the HTTP MJPEG stream server. The TCP listener stays
    # closed until the first call (start/stop/status/snapshot) to avoid
    # holding a second port when streaming isn't being used.
    def stream_server
      @stream_server ||= StreamServer.new
    end

    def start
      stop if @timer_id
      @timer_id = UI.start_timer(0.1, true) do
        @transport.poll do |msg, transport|
          process_message(msg, transport)
        end
      end
      Logger.info("SU MCP Bridge Server started on port #{@port} (v#{PLUGIN_VERSION})")
    end

    def stop
      UI.stop_timer(@timer_id) if @timer_id
      @timer_id = nil
      Logger.info("Server stopped")
    end

    # --------------------------------------------------------------------
    # Handler registration
    # --------------------------------------------------------------------
    def build_handlers
      {
        # System
        "ping"                  => method(:handle_ping),
        "hello"                 => method(:handle_hello),

        # Walls
        "ops.wall.create"       => ->(p) { Ops::Wall.create(p) },
        "ops.wall.modify"       => ->(p) { Ops::Wall.modify(p) },
        "ops.wall.delete"       => ->(p) { Ops::Wall.delete(p) },

        # Openings
        "ops.opening.cut"       => ->(p) { Ops::Opening.cut(p) },
        "ops.opening.batch_cut" => ->(p) { Ops::Opening.batch_cut(p) },
        "ops.opening.modify"    => ->(p) { Ops::Opening.modify(p) },
        "ops.opening.delete"    => ->(p) { Ops::Opening.delete(p) },

        # Slabs
        "ops.slab.create"       => ->(p) { Ops::Slab.create(p) },
        "ops.slab.delete"       => ->(p) { Ops::Slab.delete(p) },

        # Roofs
        "ops.roof.create"       => ->(p) { Ops::Roof.create(p) },
        "ops.roof.delete"       => ->(p) { Ops::Roof.delete(p) },

        # Primitives
        "ops.primitive.create"  => ->(p) { Ops::PrimitiveOps.create(p) },

        # Components
        "ops.component.place"   => ->(p) { Ops::Component.place(p) },
        "ops.component.delete" => ->(p) { Ops::Component.delete(p) },

        # Materials & layers
        "ops.material.upsert"   => ->(p) { Ops::Material.upsert(p) },
        "ops.material.assign"   => ->(p) { Ops::Material.assign(p) },
        "ops.layer.upsert"      => ->(p) { Ops::Layer.upsert(p) },
        "ops.layer.assign"      => ->(p) { Ops::Layer.assign(p) },

        # Generic delete + set_material (back-compat)
        "ops.delete"            => ->(p) { Ops::Query.delete(p) },
        "ops.set_material"      => ->(p) { Ops::Query.set_material(p) },

        # Batch
        "ops.batch"             => method(:handle_batch),

        # Lifecycle
        "ops.clear_model"       => ->(p) { Ops::Capture.clear_model(p) },

        # Captures
        "view.capture"           => ->(p) { Ops::Capture.take(p) },
        "view.capture_canonical" => ->(p) { Ops::Capture.canonical(p) },

        # Live view — inline snapshot for AI + HTTP MJPEG for human observer
        "view.snapshot"          => ->(p) { Ops::Stream.snapshot(p) },
        "view.stream.start"     => ->(p) {
          srv = stream_server
          srv.start(fps: p['fps'])
          {
            'status'     => 'started',
            'port'       => srv.port,
            'url'        => srv.url,
            'stream_url' => srv.stream_url,
            'fps'        => srv.target_fps
          }
        },
        "view.stream.stop"      => ->(_p) {
          if @stream_server
            @stream_server.stop
            { 'status' => 'stopped', 'port' => @stream_server.port }
          else
            { 'status' => 'not_started' }
          end
        },
        "view.stream.status"    => ->(_p) {
          if @stream_server
            srv = @stream_server
            {
              'running'  => srv.running?,
              'port'     => srv.port,
              'url'      => srv.url,
              'stream_url' => srv.stream_url,
              'fps'      => srv.target_fps,
              'clients'  => srv.client_count
            }.merge(Ops::Stream.status)
          else
            { 'running' => false, 'port' => nil }.merge(Ops::Stream.status)
          end
        },
        "view.stream.configure" => ->(p) { Ops::Stream.configure(p) },

        # View control — camera, selection, isolation
        "view.orbit"           => ->(p) { Ops::ViewControl.orbit(p) },
        "view.zoom"            => ->(p) { Ops::ViewControl.zoom(p) },
        "view.zoom_extents"    => ->(p) { Ops::ViewControl.zoom_extents(p) },
        "view.zoom_selection"  => ->(p) { Ops::ViewControl.zoom_selection(p) },
        "view.pan"             => ->(p) { Ops::ViewControl.pan(p) },
        "view.set_camera"      => ->(p) { Ops::ViewControl.set_camera(p) },
        "view.get_camera"      => ->(p) { Ops::ViewControl.get_camera(p) },
        "selection.select"     => ->(p) { Ops::ViewControl.select(p) },
        "selection.deselect"   => ->(p) { Ops::ViewControl.deselect(p) },
        "selection.clear"      => ->(p) { Ops::ViewControl.clear_selection(p) },
        "selection.info"       => ->(p) { Ops::ViewControl.selection_info(p) },
        "view.isolate"         => ->(p) { Ops::ViewControl.isolate(p) },
        "view.unisolate"       => ->(p) { Ops::ViewControl.unisolate(p) },

        # Queries
        "query.export_json"     => ->(p) { Ops::Query.export_json(p) },
        "query.verify"          => ->(p) { Ops::Query.verify(p) },
        "query.scene_summary"   => ->(p) { Ops::Query.scene_summary(p) },
        "query.entity"          => ->(p) { Ops::Query.entity(p) },
        "query.cache_stats"     => ->(_p) { AI_ID.stats },

        # Dimensions
        "ops.dimension.create"  => ->(p) { Ops::Dimension.create(p) },

        # Lifecycle
        "lifecycle.save"        => ->(p) { Ops::Lifecycle.save(p) },
        "lifecycle.save_as"     => ->(p) { Ops::Lifecycle.save_as(p) },
        "lifecycle.new"         => ->(_p) { Ops::Lifecycle.new_file(_p) },
        "lifecycle.open"        => ->(p) { Ops::Lifecycle.open_file(p) },
        "lifecycle.close"       => ->(_p) { Ops::Lifecycle.close(_p) },
        "lifecycle.model_info"  => ->(_p) { Ops::Lifecycle.model_info(_p) },

        # Clash detection
        "query.clash_detect"    => ->(p) { Ops::Clash.detect(p) },

        # Deep scan
        "query.deep_scan"       => ->(p) { Ops::Query.deep_scan(p) },

        # Animation
        "view.walkthrough"      => ->(p) { Ops::Animation.walkthrough(p) },

        # Attribute DB (Phase 2)
        "query.attr.get"        => ->(p) { Ops::Attr.get(p) },
        "query.attr.list"       => ->(p) { Ops::Attr.list(p) },
        "query.attr.find"       => ->(p) { Ops::Attr.find(p) },
        "ops.attr.set"          => ->(p) { Ops::Attr.set(p) },
        "ops.attr.set_bulk"     => ->(p) { Ops::Attr.set_bulk(p) },
        
        # Raw Execution
        "ops.execute_ruby"      => ->(p) { Ops::Execute.run_ruby(p) }
      }
    end

    # --------------------------------------------------------------------
    # Message dispatch
    # --------------------------------------------------------------------
    private

    def process_message(msg_str, transport)
      req = nil
      begin
        req = JSON.parse(msg_str)
      rescue JSON::ParserError => e
        transport.send_message(JSON.generate(
          Envelope.error(nil, Envelope::PARSE_ERROR, "Parse error: #{e.message}")
        ))
        return
      end

      id     = req["id"]
      method = req["method"]
      params = req["params"] || {}

      handler = @handlers[method]
      unless handler
        transport.send_message(JSON.generate(
          Envelope.error(id, Envelope::METHOD_NOT_FOUND, "Method not found: #{method}")
        ))
        return
      end

      begin
        result = handler.call(params)
        envelope = Envelope.from_handler_result(id, result)
        transport.send_message(JSON.generate(envelope))
      rescue => e
        Logger.error("dispatch #{method}: #{e.message}")
        Logger.debug(e.backtrace.first(5).join("\n"))
        transport.send_message(JSON.generate(Envelope.from_exception(id, e)))
      end
    end

    # --------------------------------------------------------------------
    # System handlers
    # --------------------------------------------------------------------
    def handle_ping(_params)
      { "pong" => true, "time" => Time.now.to_f, "plugin_version" => PLUGIN_VERSION }
    end

    def handle_hello(params)
      Logger.info("hello from client v#{params['client_version']}")
      {
        "protocol_version" => PROTOCOL_VERSION,
        "plugin_version"   => PLUGIN_VERSION,
        "capabilities"     => @handlers.keys.sort
      }
    end

    # --------------------------------------------------------------------
    # Batch — run N ops with configurable failure isolation
    #
    # mode: "atomic" (default) — all ops share one undo step; any failure
    #   aborts the whole batch and raises.
    # mode: "best_effort" — each op is independent; failures become inline
    #   error entries in the result array so partial progress is preserved.
    # --------------------------------------------------------------------
    def handle_batch(params)
      ops  = params["ops"] || []
      mode = (params["mode"] || "atomic").to_s
      results = []
      t0 = Time.now.to_f

      if mode == "atomic"
        Sketchup.active_model.start_operation("AI Batch (#{ops.size})", true, false, true)
        begin
          ops.each_with_index do |op, idx|
            h = @handlers[op["method"]]
            unless h
              raise "Batch failed at index #{idx}: Unknown method '#{op['method']}'"
            end
            begin
              res = h.call(op["params"] || {})
              if res.is_a?(Hash) && res["error"]
                raise "Batch failed at index #{idx} (#{op['method']}): #{res['error']}"
              end
              results << res
            rescue => e
              Logger.warn("batch sub-op [#{idx}] #{op['method']} raised: #{e.message}")
              raise
            end
          end
          Sketchup.active_model.commit_operation
        rescue => e
          Sketchup.active_model.abort_operation
          Logger.error("batch aborted: #{e.message}")
          raise e
        end
      else
        # best_effort: each op runs independently; errors become result entries
        ops.each_with_index do |op, idx|
          h = @handlers[op["method"]]
          unless h
            results << { "error" => "Unknown method '#{op['method']}'", "index" => idx }
            next
          end
          begin
            res = h.call(op["params"] || {})
            results << (res.is_a?(Hash) ? res : { "result" => res })
          rescue => e
            Logger.warn("batch/best_effort [#{idx}] #{op['method']}: #{e.message}")
            results << { "error" => e.message, "index" => idx, "method" => op["method"] }
          end
        end
      end

      SUMCPBridge::Metrics.last_batch_time_ms = ((Time.now.to_f - t0) * 1000).round
      results
    end
  end

  @server ||= Server.new
  @server.start

  unless file_loaded?(__FILE__)
    menu = UI.menu('Extensions').add_submenu('SU MCP Bridge')
    
    menu.add_item('Dashboard & Logs') do
      require_relative 'dashboard'
      SUMCPBridge::Dashboard.show(@server)
    end
    
    menu.add_item('Ruby Console (Developer)') do
      SKETCHUP_CONSOLE.show
    end
    
    menu.add_item('Configure Port...') do
      prompts = ["WebSocket Port: "]
      defaults = [@server.port.to_s]
      input = UI.inputbox(prompts, defaults, "Configure Bridge Port")
      if input && input[0]
        new_port = input[0].to_i
        Sketchup.write_default("SU_MCP_Bridge", "port", new_port)
        @server.stop
        @server = Server.new(new_port)
        @server.start
        UI.messagebox("Port changed to #{new_port}. Server restarted.")
      end
    end
    
    menu.add_separator

    menu.add_item('Open Live View in Browser') do
      begin
        srv = @server.stream_server
        srv.start(fps: 5) unless srv.running?
        UI.openURL(srv.url)
      rescue => e
        UI.messagebox("Live View failed: #{e.message}")
      end
    end

    menu.add_item('Stop Live View') do
      if @server.instance_variable_get(:@stream_server)
        @server.stream_server.stop
        UI.messagebox('Live View stopped')
      else
        UI.messagebox('Live View was not running')
      end
    end

    menu.add_separator

    menu.add_item('Restart Server') { @server.stop; @server.start; UI.messagebox('Bridge Restarted') }
    menu.add_item('Stop Server')    { @server.stop;  UI.messagebox('Bridge Stopped') }
    menu.add_item('Cache Stats')    { UI.messagebox(AI_ID.stats.to_s) }
    file_loaded(__FILE__)
  end
end
