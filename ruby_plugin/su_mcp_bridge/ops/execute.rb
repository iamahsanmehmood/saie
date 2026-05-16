module SUMCPBridge
  module Ops
    module Execute
      def self.run_ruby(params)
        code = params["code"]
        raise "No Ruby code provided" unless code && !code.empty?
        
        begin
          # Execute the code in the global scope so it has access to Sketchup, UI, etc.
          result = eval(code, TOPLEVEL_BINDING)
          return { "success" => true, "result" => result.inspect }
        rescue Exception => e
          return { "success" => false, "error" => e.message, "backtrace" => e.backtrace }
        end
      end
    end
  end
end
