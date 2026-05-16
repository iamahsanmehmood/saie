require 'json'

module SUMCPBridge
  # SAIE Dashboard — the in-SketchUp control panel.
  #
  # Shows live bridge status, live-view stream controls, performance metrics,
  # log tail, and quick links to config / docs. Built as a single self-contained
  # HtmlDialog so we don't ship any external web assets.
  module Dashboard
    @dialog = nil

    def self.show(server)
      if @dialog && @dialog.visible?
        @dialog.bring_to_front
        return
      end

      html = build_html(server)

      opts = {
        dialog_title:    'SAIE Dashboard',
        preferences_key: 'saie_dashboard',
        scrollable:      false,
        resizable:       true,
        width:           720,
        height:          560,
        min_width:       520,
        min_height:      400,
        style:           UI::HtmlDialog::STYLE_DIALOG
      }
      @dialog = UI::HtmlDialog.new(opts)
      @dialog.set_html(html)

      register_callbacks(server)

      sub_id = SUMCPBridge::Logger.subscribe do |level, msg, ts|
        if @dialog && @dialog.visible?
          @dialog.execute_script("appendLog('#{level.to_s.upcase}', '#{jse(msg)}', '#{ts}');")
        end
      end

      @dialog.set_on_closed do
        SUMCPBridge::Logger.unsubscribe(sub_id)
        @dialog = nil
      end

      @dialog.show

      UI.start_timer(0.2, false) do
        push_stats(server)
        SUMCPBridge::Logger.history.each do |entry|
          @dialog.execute_script("appendLog('#{entry[:level].to_s.upcase}', '#{jse(entry[:msg])}', '#{entry[:ts]}');")
        end
      end
    end

    # ─── HTML / CSS / JS ──────────────────────────────────────────────────────

    def self.build_html(server)
      version = SUMCPBridge::PLUGIN_VERSION
      <<~HTML
        <!DOCTYPE html>
        <html><head><meta charset="utf-8"><title>SAIE Dashboard</title>
        <style>#{css}</style>
        </head><body>
        <header>
          <div class="brand">
            <div class="logo">SAIE</div>
            <div class="subtitle">SketchUp Automation &amp; Intelligence Engine</div>
          </div>
          <div id="status-badge" class="badge ok">
            <span class="dot"></span>BRIDGE ACTIVE
          </div>
        </header>

        <nav class="tabs">
          <button class="active" data-tab="t-overview">Overview</button>
          <button data-tab="t-stream">Live View</button>
          <button data-tab="t-logs">Logs</button>
          <button data-tab="t-config">Config</button>
          <button data-tab="t-about">About</button>
        </nav>

        <main class="content">
          <!-- OVERVIEW -->
          <section id="t-overview" class="tab active">
            <div class="grid">
              <div class="card">
                <h2>WebSocket Bridge</h2>
                <div class="row"><span>Port</span><span class="val" id="v-port">…</span></div>
                <div class="row"><span>Host</span><span class="val" id="v-host">…</span></div>
                <div class="row"><span>Protocol</span><span class="val">JSON-RPC 2.0</span></div>
                <div class="row"><span>Plugin Version</span><span class="val">v#{version}</span></div>
              </div>
              <div class="card">
                <h2>Live View Stream</h2>
                <div class="row"><span>Status</span><span class="val" id="v-stream-status">…</span></div>
                <div class="row"><span>Port</span><span class="val" id="v-stream-port">…</span></div>
                <div class="row"><span>FPS</span><span class="val" id="v-stream-fps">…</span></div>
                <div class="row"><span>Clients</span><span class="val" id="v-stream-clients">…</span></div>
              </div>
              <div class="card">
                <h2>Performance</h2>
                <div class="row"><span>Last batch</span><span class="val" id="v-batch">…</span></div>
                <div class="row"><span>Tracked entities</span><span class="val" id="v-cache-total">…</span></div>
                <div class="row"><span>Orphans purged</span><span class="val" id="v-cache-purged">…</span></div>
              </div>
              <div class="card">
                <h2>MCP Tools</h2>
                <div class="row"><span>Handlers registered</span><span class="val" id="v-handlers">…</span></div>
                <div class="row"><span>Config source</span><span class="val mono" id="v-config-src">…</span></div>
              </div>
            </div>
            <div class="actions">
              <button class="btn" onclick="sketchup.refreshStats()">Refresh</button>
              <button class="btn primary" onclick="sketchup.restartServer()">Restart Bridge</button>
              <button class="btn" onclick="sketchup.openDocs()">Docs ↗</button>
            </div>
          </section>

          <!-- LIVE VIEW -->
          <section id="t-stream" class="tab">
            <div class="card">
              <h2>HTTP MJPEG Stream</h2>
              <p class="hint">A browser-friendly live view of the SketchUp viewport. Share the URL with anyone on this machine to let them watch you work.</p>
              <div class="row"><span>URL</span><span class="val mono" id="v-stream-url">—</span></div>
              <div class="actions">
                <button class="btn primary" onclick="sketchup.streamStart()">Start Stream</button>
                <button class="btn" onclick="sketchup.streamStop()">Stop</button>
                <button class="btn" onclick="sketchup.openLiveView()">Open in Browser ↗</button>
              </div>
            </div>
            <div class="card">
              <h2>Capture Source</h2>
              <p class="hint">
                <strong>window</strong> — reads SketchUp's framebuffer; includes axes, selection highlights, gizmos.<br>
                <strong>view</strong> — clean offline render via View#write_image; no overlays.
              </p>
            </div>
          </section>

          <!-- LOGS -->
          <section id="t-logs" class="tab">
            <div class="logs-header">
              <span class="hint">Real-time RPC traffic, agent calls, plugin events.</span>
              <button class="btn small" onclick="document.getElementById('log-container').innerHTML=''">Clear</button>
            </div>
            <div id="log-container"></div>
          </section>

          <!-- CONFIG -->
          <section id="t-config" class="tab">
            <div class="card">
              <h2>Configuration File</h2>
              <p class="hint">All settings (ports, paths, defaults) live in <code>saie.toml</code>. Edit it, then restart the bridge for changes to apply.</p>
              <div class="row"><span>Resolved from</span><span class="val mono" id="v-config-src-2">…</span></div>
              <div class="actions">
                <button class="btn primary" onclick="sketchup.openConfig()">Open saie.toml</button>
                <button class="btn" onclick="sketchup.copyConfigPath()">Copy Path</button>
              </div>
            </div>
            <div class="card">
              <h2>Environment Variable Overrides</h2>
              <p class="hint">Any setting can be overridden at launch time with <code>SAIE_&lt;SECTION&gt;_&lt;KEY&gt;</code>, e.g.:</p>
              <pre>SAIE_BRIDGE_PORT=9999
SAIE_STREAM_FPS=10
SAIE_AGENTS_DEFAULT_PROVIDER=ollama</pre>
            </div>
          </section>

          <!-- ABOUT -->
          <section id="t-about" class="tab">
            <div class="about">
              <div class="logo-big">SAIE</div>
              <p class="tagline">SketchUp Automation &amp; Intelligence Engine</p>
              <p class="version">v#{version}</p>
              <p class="desc">
                A bridge between AI agents (Claude, Ollama) and SketchUp 2025 over the
                Model Context Protocol. Strict declarative JSON-RPC over WebSocket —
                no raw Ruby eval required for normal operation.
              </p>
              <div class="links">
                <a href="#" onclick="sketchup.openRepo()">GitHub ↗</a>
                <a href="#" onclick="sketchup.openDocs()">Documentation ↗</a>
                <a href="#" onclick="sketchup.openMCP()">MCP Spec ↗</a>
              </div>
            </div>
          </section>
        </main>

        <script>#{js}</script>
        </body></html>
      HTML
    end

    def self.css
      <<~CSS
        :root {
          --bg:        #0f1115;
          --panel:     #1a1d24;
          --panel-2:   #232730;
          --border:    #2a2f3a;
          --text:      #e5e7eb;
          --muted:     #8b92a3;
          --accent:    #00d2ff;
          --accent-2:  #3a82f6;
          --success:   #4ade80;
          --warn:      #facc15;
          --error:     #f87171;
        }
        * { box-sizing: border-box; }
        body {
          margin: 0; padding: 0;
          font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
          background: var(--bg); color: var(--text);
          display: flex; flex-direction: column; height: 100vh; overflow: hidden;
          font-size: 13px;
        }
        header {
          background: var(--panel); padding: 14px 20px;
          border-bottom: 1px solid var(--border);
          display: flex; justify-content: space-between; align-items: center;
        }
        .brand { display: flex; align-items: center; gap: 12px; }
        .logo {
          font-size: 22px; font-weight: 800; letter-spacing: 2px;
          background: linear-gradient(135deg, var(--accent), var(--accent-2));
          -webkit-background-clip: text; background-clip: text; color: transparent;
        }
        .subtitle { color: var(--muted); font-size: 11px; }
        .badge {
          display: flex; align-items: center; gap: 6px;
          padding: 5px 10px; border-radius: 100px; font-size: 10px;
          font-weight: 700; letter-spacing: 1px;
        }
        .badge.ok { background: rgba(74,222,128,0.12); color: var(--success); }
        .dot {
          width: 7px; height: 7px; border-radius: 50%;
          background: var(--success); box-shadow: 0 0 6px var(--success);
          animation: pulse 1.6s infinite;
        }
        @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:0.4 } }

        .tabs {
          background: var(--panel); border-bottom: 1px solid var(--border);
          display: flex; padding: 0 12px;
        }
        .tabs button {
          background: transparent; border: none; color: var(--muted);
          padding: 11px 16px; cursor: pointer; font-size: 13px;
          border-bottom: 2px solid transparent; transition: all 0.15s;
        }
        .tabs button:hover { color: var(--text); }
        .tabs button.active { color: var(--accent); border-bottom-color: var(--accent); }

        .content { flex: 1; overflow-y: auto; padding: 18px 20px; }
        .tab { display: none; animation: fade 0.2s ease; }
        .tab.active { display: block; }
        @keyframes fade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

        .grid {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
          gap: 14px;
        }
        .card {
          background: var(--panel); border: 1px solid var(--border);
          border-radius: 8px; padding: 14px 16px; margin-bottom: 14px;
        }
        .card h2 {
          margin: 0 0 10px 0; font-size: 11px; text-transform: uppercase;
          letter-spacing: 1.5px; color: var(--muted); font-weight: 600;
        }
        .row {
          display: flex; justify-content: space-between; align-items: center;
          padding: 5px 0; border-bottom: 1px dashed var(--border);
        }
        .row:last-child { border-bottom: none; }
        .row span:first-child { color: var(--muted); }
        .val { font-weight: 600; color: var(--text); }
        .val.mono, code, pre { font-family: 'Consolas', 'Cascadia Mono', monospace; }
        .hint { color: var(--muted); font-size: 12px; line-height: 1.5; margin: 0 0 10px; }
        pre {
          background: #0a0c10; border: 1px solid var(--border); border-radius: 6px;
          padding: 10px 12px; font-size: 11px; color: #c9d1d9; margin: 6px 0 0;
          overflow-x: auto;
        }

        .actions { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
        .btn {
          background: var(--panel-2); border: 1px solid var(--border); color: var(--text);
          padding: 7px 14px; border-radius: 6px; cursor: pointer;
          font-size: 12px; transition: all 0.15s; font-weight: 500;
        }
        .btn:hover { background: #2c3140; border-color: var(--accent); }
        .btn.primary {
          background: linear-gradient(135deg, var(--accent), var(--accent-2));
          border: none; color: #06121b; font-weight: 600;
        }
        .btn.primary:hover { filter: brightness(1.1); }
        .btn.small { padding: 3px 8px; font-size: 11px; }

        .logs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
        #log-container {
          background: #06080c; border: 1px solid var(--border); border-radius: 6px;
          padding: 10px 12px; font-family: 'Consolas', 'Cascadia Mono', monospace;
          font-size: 11px; height: calc(100vh - 230px); overflow-y: auto;
        }
        .log-line { padding: 2px 0; line-height: 1.45; border-bottom: 1px solid #0d1117; }
        .log-line:last-child { border-bottom: none; }
        .log-ts { color: #555e6b; margin-right: 6px; }
        .log-INFO { color: var(--accent); }
        .log-WARN { color: var(--warn); }
        .log-ERROR { color: var(--error); }
        .log-DEBUG { color: #6b7280; }
        .log-msg { color: #c9d1d9; margin-left: 4px; }

        .about { text-align: center; padding: 30px 20px; }
        .logo-big {
          font-size: 56px; font-weight: 800; letter-spacing: 6px;
          background: linear-gradient(135deg, var(--accent), var(--accent-2));
          -webkit-background-clip: text; background-clip: text; color: transparent;
          margin-bottom: 4px;
        }
        .tagline { color: var(--muted); font-size: 13px; margin: 0 0 6px; }
        .version { color: var(--accent); font-weight: 700; font-size: 13px; }
        .desc { color: var(--muted); max-width: 480px; margin: 24px auto; line-height: 1.65; }
        .links { display: flex; justify-content: center; gap: 18px; margin-top: 18px; }
        .links a { color: var(--accent); text-decoration: none; font-weight: 500; }
        .links a:hover { text-decoration: underline; }
      CSS
    end

    def self.js
      <<~JS
        document.querySelectorAll('.tabs button').forEach(b => {
          b.addEventListener('click', () => {
            document.querySelectorAll('.tabs button').forEach(x => x.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(x => x.classList.remove('active'));
            b.classList.add('active');
            document.getElementById(b.dataset.tab).classList.add('active');
          });
        });

        function appendLog(level, msg, ts) {
          const c = document.getElementById('log-container');
          const d = document.createElement('div');
          d.className = 'log-line';
          d.innerHTML =
            '<span class="log-ts">[' + ts + ']</span>' +
            '<span class="log-' + level + '">[' + level + ']</span>' +
            '<span class="log-msg">' + escapeHtml(msg) + '</span>';
          c.appendChild(d);
          if (c.scrollHeight - c.scrollTop < c.clientHeight + 60) c.scrollTop = c.scrollHeight;
          while (c.children.length > 500) c.removeChild(c.firstChild);
        }

        function updateStats(s) {
          set('v-port', s.port);
          set('v-host', s.host);
          set('v-handlers', s.handlers);
          set('v-batch', s.batch_time_ms ? s.batch_time_ms + ' ms' : '—');
          set('v-cache-total', s.cache_total);
          set('v-cache-purged', s.cache_purged);
          set('v-config-src', s.config_source);
          set('v-config-src-2', s.config_source);
          set('v-stream-status', s.stream_running ? 'running' : 'stopped');
          set('v-stream-port', s.stream_port || '—');
          set('v-stream-fps', s.stream_fps || '—');
          set('v-stream-clients', s.stream_clients ?? '—');
          set('v-stream-url', s.stream_url || '—');
        }

        function set(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }

        function escapeHtml(u) {
          return String(u)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
        }
      JS
    end

    # ─── Callbacks ────────────────────────────────────────────────────────────

    def self.register_callbacks(server)
      @dialog.add_action_callback('refreshStats')  { |_ctx| push_stats(server) }
      @dialog.add_action_callback('restartServer') do |_ctx|
        server.stop; server.start
        push_stats(server)
        SUMCPBridge::Logger.info('Bridge restarted from dashboard.')
      end
      @dialog.add_action_callback('streamStart') do |_ctx|
        srv = server.stream_server
        srv.start(fps: SUMCPBridge::Config.stream[:fps]) unless srv.running?
        push_stats(server)
      end
      @dialog.add_action_callback('streamStop') do |_ctx|
        srv = server.instance_variable_get(:@stream_server)
        srv.stop if srv
        push_stats(server)
      end
      @dialog.add_action_callback('openLiveView') do |_ctx|
        srv = server.stream_server
        srv.start(fps: SUMCPBridge::Config.stream[:fps]) unless srv.running?
        UI.openURL(srv.url)
      end
      @dialog.add_action_callback('openConfig') do |_ctx|
        path = SUMCPBridge::Config.source
        if path && File.exist?(path)
          UI.openURL("file:///#{path.gsub('\\', '/')}")
        else
          UI.messagebox("Config file not found.\nResolved source: #{path}")
        end
      end
      @dialog.add_action_callback('copyConfigPath') do |_ctx|
        # No clipboard API in HtmlDialog — show a messagebox instead
        UI.messagebox("Config path:\n#{SUMCPBridge::Config.source}")
      end
      @dialog.add_action_callback('openRepo') { |_ctx| UI.openURL('https://github.com/iamahsanmehmood/saie') }
      @dialog.add_action_callback('openDocs') { |_ctx| UI.openURL('https://github.com/iamahsanmehmood/saie/tree/main/docs') }
      @dialog.add_action_callback('openMCP')  { |_ctx| UI.openURL('https://modelcontextprotocol.io/') }
    end

    # ─── Stats payload ────────────────────────────────────────────────────────

    def self.push_stats(server)
      return unless @dialog && @dialog.visible?

      stream_running = false
      stream_port    = nil
      stream_url     = nil
      stream_fps     = nil
      stream_clients = 0
      ss = server.instance_variable_get(:@stream_server)
      if ss
        stream_running = ss.running?
        stream_port    = ss.port
        stream_url     = ss.url
        stream_fps     = ss.target_fps
        stream_clients = ss.client_count
      end

      c_stats = SUMCPBridge::AI_ID.stats
      handlers = server.instance_variable_get(:@handlers)&.size || 0

      stats = {
        port:           server.port,
        host:           SUMCPBridge::Config.bridge[:host],
        handlers:       handlers,
        cache_total:    c_stats[:total_tracked],
        cache_purged:   c_stats[:purged_orphans],
        batch_time_ms:  SUMCPBridge::Metrics.last_batch_time_ms || 0,
        config_source:  SUMCPBridge::Config.source,
        stream_running: stream_running,
        stream_port:    stream_port,
        stream_url:     stream_url,
        stream_fps:     stream_fps,
        stream_clients: stream_clients
      }
      @dialog.execute_script("updateStats(#{stats.to_json});")
    end

    def self.jse(str)
      str.to_s.gsub('\\', '\\\\').gsub("'", "\\\\'").gsub("\n", '\\n').gsub("\r", '')
    end
  end
end
