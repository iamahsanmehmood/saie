module SUMCPBridge
  # Centralized logger. Replaces scattered `puts` calls.
  #
  # Levels: :debug, :info, :warn, :error
  # Set the threshold via `SUMCPBridge::Logger.level = :debug` from the Ruby
  # console; default is :info.
  module Logger
    LEVELS = { debug: 0, info: 1, warn: 2, error: 3 }.freeze

    @level = :info

    class << self
      attr_accessor :level

      def debug(msg); _emit(:debug, msg); end
      def info(msg);  _emit(:info,  msg); end
      def warn(msg);  _emit(:warn,  msg); end
      def error(msg); _emit(:error, msg); end

      def _emit(level, msg)
        return if LEVELS[level] < LEVELS[@level]
        ts = Time.now.strftime("%H:%M:%S")
        
        @history ||= []
        @history << { level: level, msg: msg, ts: ts }
        @history.shift if @history.size > 500 # Keep last 500 logs
        
        @subscribers ||= {}
        @subscribers.each_value { |cb| cb.call(level, msg, ts) }
        
        tag = level.to_s.upcase.ljust(5)
        STDOUT.puts "[SUMCPBridge #{ts} #{tag}] #{msg}"
        STDOUT.flush
      end

      def history
        @history || []
      end

      def subscribe(&block)
        @subscribers ||= {}
        id = Object.new
        @subscribers[id] = block
        id
      end

      def unsubscribe(id)
        @subscribers.delete(id) if @subscribers
      end
    end
  end

  module Metrics
    @last_batch_time_ms = 0
    @last_ping_latency_ms = 0

    class << self
      attr_accessor :last_batch_time_ms
      attr_accessor :last_ping_latency_ms
    end
  end
end
