require 'json'

# SAIE central configuration loader (Ruby side).
#
# Mirrors src/su_mcp_bridge/core/config.py — both halves of SAIE read the same
# saie.toml so ports/paths/options stay in sync without manual coordination.
#
# Resolution order (first hit wins):
#   1. ENV['SAIE_CONFIG'] (absolute path)
#   2. ./saie.toml in CWD
#   3. ~/.saie/saie.toml
#   4. <repo-root>/saie.toml (bundled default — found via plugin install path)
#
# Override any value with SAIE_<SECTION>_<KEY> environment variables, e.g.
#   SAIE_BRIDGE_PORT=9999          → bridge.port = 9999
#   SAIE_STREAM_FPS=12             → stream.fps  = 12
#
# We ship a hand-rolled minimal TOML parser instead of pulling a gem, because
# SketchUp ships its own Ruby and we cannot rely on the user installing gems.
module SUMCPBridge
  module Config
    DEFAULTS = {
      bridge: {
        host:       '127.0.0.1',
        port:       9876,
        port_range: 10,
        port_file:  '~/.saie_port',
        timeout:    30.0
      },
      stream: {
        enabled:    true,
        port:       9877,
        port_range: 10,
        source:     'window',
        fps:        5,
        quality:    70,
        width:      800,
        height:     600,
        cache_ms:   100
      },
      sketchup: {
        version:          '2025',
        install_path:     '',
        plugins_path:     '',
        autostart_bridge: true
      },
      projects: {
        root:    '~/Documents/SAIE_Projects',
        subdirs: %w[model captures reports data/scan_history assets]
      },
      capture: {
        default_preset:     'iso',
        default_resolution: 'med',
        default_style:      'default',
        isolation_margin:   0.15
      },
      agents: {
        default_provider:        'anthropic',
        default_anthropic_model: 'claude-sonnet-4-5-20250929',
        default_ollama_model:    'gemma3:4b',
        ollama_host:             'http://localhost:11434'
      },
      logging: {
        level:            'info',
        ring_buffer_size: 500,
        file:             ''
      },
      security: {
        localhost_only: true,
        auth_token:     ''
      },
      experimental: {
        enable_raw_ruby_exec:     true,
        enable_walkthrough_video: true,
        enable_dxf_import:        true
      }
    }.freeze

    @cached  = nil
    @source  = '<defaults>'

    class << self
      attr_reader :source

      # Return the cached config hash, loading on first access.
      # Pass reload: true to force re-reading from disk.
      def get(reload: false)
        @cached = nil if reload
        @cached ||= load
      end

      # Convenience accessors so call sites don't have to dig through hashes.
      def bridge;       get[:bridge];       end
      def stream;       get[:stream];       end
      def sketchup;     get[:sketchup];     end
      def projects;     get[:projects];     end
      def capture;      get[:capture];      end
      def agents;       get[:agents];       end
      def logging;      get[:logging];      end
      def security;     get[:security];     end
      def experimental; get[:experimental]; end

      # ── Path helpers ─────────────────────────────────────────────────────
      def port_file_path
        File.expand_path(bridge[:port_file])
      end

      def projects_root_path
        File.expand_path(projects[:root])
      end

      private

      def load
        merged = deep_dup(DEFAULTS)
        path   = find_config_file
        if path
          parsed = parse_toml(File.read(path))
          deep_merge!(merged, parsed)
          @source = path
        end
        apply_env_overrides!(merged)
        merged
      end

      def find_config_file
        candidates = []
        candidates << ENV['SAIE_CONFIG'] if ENV['SAIE_CONFIG'] && !ENV['SAIE_CONFIG'].empty?
        candidates << File.join(Dir.pwd, 'saie.toml')
        candidates << File.expand_path('~/.saie/saie.toml')
        # Repo-bundled default — two dirs up from this file
        candidates << File.expand_path('../../../saie.toml', __FILE__)
        candidates.compact.uniq.each do |c|
          return c if File.file?(c)
        end
        nil
      end

      def apply_env_overrides!(cfg)
        cfg.each do |section, table|
          table.each_key do |key|
            env_key = "SAIE_#{section.to_s.upcase}_#{key.to_s.upcase}"
            raw = ENV[env_key]
            next if raw.nil?
            current = table[key]
            table[key] = coerce(raw, current)
          end
        end
      end

      def coerce(raw, sample)
        case sample
        when TrueClass, FalseClass then %w[1 true yes on].include?(raw.to_s.downcase.strip)
        when Integer               then raw.to_i
        when Float                 then raw.to_f
        when Array                 then raw.split(',').map(&:strip).reject(&:empty?)
        else raw
        end
      end

      def deep_dup(h)
        h.each_with_object({}) do |(k, v), acc|
          acc[k] = v.is_a?(Hash) ? deep_dup(v) : (v.dup rescue v)
        end
      end

      def deep_merge!(dst, src)
        src.each do |k, v|
          if dst[k].is_a?(Hash) && v.is_a?(Hash)
            deep_merge!(dst[k], v)
          else
            dst[k] = v
          end
        end
        dst
      end

      # ── Minimal TOML parser ─────────────────────────────────────────────
      # Handles the subset we use: [sections], key = "string"/int/float/bool,
      # and inline arrays of strings. Not a full TOML 1.0 implementation —
      # just enough for saie.toml. Comments (#) and blank lines are skipped.
      def parse_toml(text)
        result  = {}
        section = nil
        text.each_line do |raw|
          line = raw.split('#', 2).first.to_s.strip
          next if line.empty?

          if line.start_with?('[') && line.end_with?(']')
            name = line[1..-2].strip
            section = name.to_sym
            result[section] ||= {}
            next
          end

          next unless section
          k, _, v = line.partition('=')
          next if v.empty?
          key   = k.strip.to_sym
          value = parse_value(v.strip)
          result[section][key] = value
        end
        result
      end

      def parse_value(s)
        return s[1..-2] if (s.start_with?('"') && s.end_with?('"')) ||
                          (s.start_with?("'") && s.end_with?("'"))
        return true  if s == 'true'
        return false if s == 'false'
        if s.start_with?('[') && s.end_with?(']')
          inner = s[1..-2]
          return [] if inner.strip.empty?
          return split_array(inner).map { |item| parse_value(item.strip) }
        end
        return Integer(s) rescue nil if s =~ /\A-?\d+\z/
        return Float(s)   rescue nil if s =~ /\A-?\d*\.\d+\z/
        s   # fallback: raw string
      end

      def split_array(inner)
        # Split on commas not inside quotes
        parts = []
        buf   = ''
        in_q  = false
        inner.each_char do |c|
          if c == '"' || c == "'"
            in_q = !in_q
            buf << c
          elsif c == ',' && !in_q
            parts << buf
            buf = ''
          else
            buf << c
          end
        end
        parts << buf unless buf.empty?
        parts
      end
    end
  end
end
