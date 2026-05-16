require_relative '../logger'

module SUMCPBridge
  module Ops
    # Attribute dictionary read/write ops.
    #
    # Every SketchUp Group/ComponentInstance carries one or more named
    # attribute_dictionaries. SAIE writes its own state into "su_mcp_bridge".
    # This module exposes the full surface so AI agents can read/write any
    # dictionary — in particular the "bim" dictionary defined in
    # docs/bim_metadata_schema.md.
    module Attr

      # -----------------------------------------------------------------------
      # query.attr.get
      # Read one key (or an entire dictionary) from an entity.
      #
      # Params:
      #   ai_id     (str)  — target entity
      #   dict_name (str)  — attribute dictionary name, e.g. "bim"
      #   key       (str)  — optional; if omitted returns the whole dict
      # -----------------------------------------------------------------------
      def self.get(params)
        ai_id     = params["ai_id"] || params["id"]
        dict_name = params["dict_name"]
        key       = params["key"]

        return { "error" => "ai_id is required" }     unless ai_id
        return { "error" => "dict_name is required" } unless dict_name

        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Entity not found: #{ai_id}" } unless ent && ent.valid?

        dict = ent.attribute_dictionary(dict_name)
        return { "ai_id" => ai_id, "dict_name" => dict_name, "data" => nil } unless dict

        if key
          value = ent.get_attribute(dict_name, key)
          { "ai_id" => ai_id, "dict_name" => dict_name, "key" => key, "value" => value }
        else
          data = {}
          dict.each_pair { |k, v| data[k] = v }
          { "ai_id" => ai_id, "dict_name" => dict_name, "data" => data }
        end
      end

      # -----------------------------------------------------------------------
      # query.attr.list
      # List all attribute dictionary names present on an entity.
      #
      # Params:
      #   ai_id (str) — target entity
      # -----------------------------------------------------------------------
      def self.list(params)
        ai_id = params["ai_id"] || params["id"]
        return { "error" => "ai_id is required" } unless ai_id

        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Entity not found: #{ai_id}" } unless ent && ent.valid?

        dicts = ent.attribute_dictionaries
        names = dicts ? dicts.map(&:name) : []
        { "ai_id" => ai_id, "dictionaries" => names }
      end

      # -----------------------------------------------------------------------
      # query.attr.find
      # Scan all tracked entities and return those whose attribute dictionary
      # contains a matching key (and optionally a matching value).
      #
      # Params:
      #   dict_name (str)  — dictionary to search in
      #   key       (str)  — attribute key that must exist
      #   value     (any)  — optional; if provided, key must equal this value
      #   type      (str)  — optional entity type filter: "wall","slab","roof"…
      # -----------------------------------------------------------------------
      def self.find(params)
        dict_name = params["dict_name"]
        key       = params["key"]
        value     = params["value"]          # nil means "any value"
        type_f    = params["type"]           # optional entity type filter
        limit     = params["limit"] ? params["limit"].to_i : nil
        max_depth = params["depth"] ? params["depth"].to_i : nil  # nil = unlimited

        return { "error" => "dict_name is required" } unless dict_name
        return { "error" => "key is required" }       unless key

        model   = Sketchup.active_model
        matches = []

        _walk_entities(model.active_entities, 0, max_depth) do |ent|
          break if limit && matches.length >= limit

          next unless ent.respond_to?(:get_attribute)

          if type_f
            ent_type = ent.get_attribute("su_mcp_bridge", "type")
            next unless ent_type == type_f
          end

          attr_value = ent.get_attribute(dict_name, key, :__missing__)
          next if attr_value == :__missing__
          next if !value.nil? && attr_value.to_s != value.to_s

          ai_id = ent.get_attribute("su_mcp_bridge", "ai_id")
          next unless ai_id

          matches << {
            "ai_id"     => ai_id,
            "dict_name" => dict_name,
            "key"       => key,
            "value"     => attr_value,
            "type"      => ent.get_attribute("su_mcp_bridge", "type")
          }
        end

        { "matches" => matches, "count" => matches.size, "limit_applied" => !limit.nil? }
      end

      # -----------------------------------------------------------------------
      # ops.attr.set
      # Write one key into an attribute dictionary on a single entity.
      #
      # Params:
      #   ai_id     (str) — target entity
      #   dict_name (str) — dictionary name, e.g. "bim"
      #   key       (str) — attribute key
      #   value     (any) — value to store (string, number, bool)
      # -----------------------------------------------------------------------
      def self.set(params)
        ai_id     = params["ai_id"] || params["id"]
        dict_name = params["dict_name"]
        key       = params["key"]
        value     = params["value"]

        return { "error" => "ai_id is required" }     unless ai_id
        return { "error" => "dict_name is required" } unless dict_name
        return { "error" => "key is required" }       unless key
        return { "error" => "value is required" }     if value.nil?

        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Entity not found: #{ai_id}" } unless ent && ent.valid?

        ent.set_attribute(dict_name, key, value)
        SUMCPBridge::Logger.debug("ops.attr.set #{ai_id}[#{dict_name}][#{key}] = #{value.inspect}")

        { "ai_id" => ai_id, "dict_name" => dict_name, "key" => key, "value" => value, "status" => "set" }
      end

      # -----------------------------------------------------------------------
      # ops.attr.set_bulk
      # Atomic multi-entity, multi-key write in a single undo step.
      #
      # Params:
      #   operations (array) — each item: { ai_id, dict_name, key, value }
      # -----------------------------------------------------------------------
      def self.set_bulk(params)
        operations = params["operations"] || []
        return { "error" => "operations array is required and must not be empty" } if operations.empty?

        model   = Sketchup.active_model
        results = []

        model.start_operation("SAIE attr.set_bulk (#{operations.size})", true)
        begin
          operations.each_with_index do |op, idx|
            ai_id     = op["ai_id"] || op["id"]
            dict_name = op["dict_name"]
            key       = op["key"]
            value     = op["value"]

            unless ai_id && dict_name && key && !value.nil?
              raise "Operation #{idx} missing required field (ai_id, dict_name, key, value)"
            end

            ent = SUMCPBridge::AI_ID.find(ai_id)
            raise "Operation #{idx}: Entity not found: #{ai_id}" unless ent && ent.valid?

            ent.set_attribute(dict_name, key, value)
            results << { "ai_id" => ai_id, "dict_name" => dict_name, "key" => key, "status" => "set" }
          end
          model.commit_operation
        rescue => e
          model.abort_operation
          SUMCPBridge::Logger.error("ops.attr.set_bulk failed: #{e.message}")
          return { "error" => e.message }
        end

        { "results" => results, "count" => results.size, "status" => "ok" }
      end

      # -----------------------------------------------------------------------
      private

      def self._walk_entities(entities, depth = 0, max_depth = nil, &block)
        return if max_depth && depth > max_depth
        entities.each do |ent|
          block.call(ent)
          if ent.respond_to?(:definition)
            _walk_entities(ent.definition.entities, depth + 1, max_depth, &block)
          elsif ent.respond_to?(:entities)
            _walk_entities(ent.entities, depth + 1, max_depth, &block)
          end
        end
      end
    end
  end
end
