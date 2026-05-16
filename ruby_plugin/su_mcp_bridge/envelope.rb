module SUMCPBridge
  # Envelope helpers — translate handler return values into JSON-RPC 2.0
  # compliant response shapes.
  #
  # Handlers return either:
  #   * a hash (treated as success; sent verbatim as the `result`)
  #   * a hash with an "error" key, e.g. {"error" => "wall not found"}
  #     (treated as a domain error; converted to a JSON-RPC error object)
  #   * raise an exception (caught by the dispatcher; converted to error)
  #
  # JSON-RPC 2.0 error codes:
  #   -32700 parse error
  #   -32600 invalid request
  #   -32601 method not found
  #   -32602 invalid params
  #   -32603 internal error
  #   -32000..-32099 server-defined application errors (we use these for domain)
  module Envelope
    # JSON-RPC standard codes
    PARSE_ERROR      = -32700
    INVALID_REQUEST  = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS   = -32602
    INTERNAL_ERROR   = -32603
    # Application codes
    APP_ERROR        = -32000   # generic domain error
    NOT_FOUND        = -32001   # entity by ai_id missing
    VALIDATION       = -32002   # invalid geometry / params
    BOOLEAN_FAILED   = -32003   # subtract returned nil
    BUSY             = -32004   # model is in another start_operation

    APP_CODE_KEYS = {
      "not_found"      => NOT_FOUND,
      "validation"     => VALIDATION,
      "boolean_failed" => BOOLEAN_FAILED,
      "busy"           => BUSY
    }.freeze

    # Build a successful JSON-RPC response object.
    def self.success(id, result)
      { "jsonrpc" => "2.0", "id" => id, "result" => result }
    end

    # Build a JSON-RPC error response.
    def self.error(id, code, message, data = nil)
      err = { "code" => code, "message" => message.to_s }
      err["data"] = data unless data.nil?
      { "jsonrpc" => "2.0", "id" => id, "error" => err }
    end

    # Translate a handler result hash into a JSON-RPC envelope.
    #
    # Design: domain-level errors (wall not found, invalid params, etc.) flow
    # through as part of the success `result` dict — handlers signal them
    # by returning {"error" => "..."}. Build scripts and the Python client
    # check `result["error"]` to detect these, which keeps existing call sites
    # working without try/except.
    #
    # The JSON-RPC outer `error` envelope is reserved for protocol-level
    # failures: parse error, method-not-found, internal exception. Those are
    # raised in main.rb's dispatcher and caught there.
    def self.from_handler_result(id, result)
      success(id, result)
    end

    # Translate a Ruby exception into a JSON-RPC error response.
    def self.from_exception(id, exception, code = INTERNAL_ERROR)
      backtrace = (exception.backtrace || []).first(5).join("\n")
      data = { "exception" => exception.class.name, "backtrace" => backtrace }
      error(id, code, exception.message, data)
    end
  end
end
