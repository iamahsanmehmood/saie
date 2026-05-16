require_relative 'logger'

module SUMCPBridge
  # AI_ID — persistent stable IDs across SketchUp boolean operations.
  #
  # Every entity that SUMCPBridge creates gets a string `ai_id` written into
  # its attribute dictionary. SketchUp Pro's `subtract` copies attribute
  # dictionaries from the larger surviving group, so the wall's `ai_id`
  # survives openings being cut from it.
  #
  # We maintain an in-memory hash {ai_id => entity} as a cache. The cache
  # is invalidated lazily: a stale entry that fails `entity.valid?` or
  # whose attribute no longer matches is auto-evicted on next lookup.
  module AI_ID
    DICT_NAME = "su_mcp_bridge".freeze
    KEY_NAME  = "ai_id".freeze

    @cache = {}
    @purged = 0

    class << self
      # ---- Setters --------------------------------------------------------

      # Write the ai_id onto an entity's attribute dictionary AND seed the cache.
      def set(entity, id, tags: [])
        return unless entity && entity.valid? && id
        entity.set_attribute(DICT_NAME, KEY_NAME, id.to_s)
        entity.set_attribute(DICT_NAME, "tags", tags.join(",")) if tags && !tags.empty?
        @cache[id.to_s] = entity
      end

      # Read the ai_id back from an entity, or nil.
      def get(entity)
        return nil unless entity && entity.valid?
        entity.get_attribute(DICT_NAME, KEY_NAME)
      end

      def get_tags(entity)
        return [] unless entity && entity.valid?
        t = entity.get_attribute(DICT_NAME, "tags")
        t ? t.split(",") : []
      end

      def auto_name(type, pt_mm = nil)
        prefix = type.to_s.upcase
        if pt_mm && pt_mm.is_a?(Array) && pt_mm.size >= 2
          x, y = pt_mm[0..1].map { |v| (v.to_f / 1000.0).round }
          idx = Time.now.to_i % 10000
          "#{prefix}_#{x}M_#{y}M_#{idx}"
        else
          @auto_counter ||= 0
          @auto_counter += 1
          "#{prefix}_#{Time.now.to_i}_#{@auto_counter}"
        end
      end

      # ---- Lookup ---------------------------------------------------------

      # Find an entity by ai_id. Cache-first, then linear scan over
      # `active_entities` (the right place — ops are added there, not to
      # `model.entities` which excludes nested groups).
      def find(id, model = Sketchup.active_model)
        return nil if id.nil?
        key = id.to_s

        # 1) Cache hit if entity is still valid AND still tagged with the id.
        cached = @cache[key]
        if cached && cached.valid? && get(cached) == key
          return cached
        end

        # 2) Stale cache entry — evict.
        if cached
          @cache.delete(key)
          @purged += 1
        end

        # 3) Slow path: scan active_entities (and one level into groups for safety).
        scan_active_entities_for(model.active_entities, key) ||
          scan_top_level_entities_for(model.entities, key)
      end

      # Replace the cached pointer for an existing ai_id. Use this after
      # boolean ops where SketchUp returns a new group with the attribute
      # already copied; this just refreshes our pointer without rescanning.
      def replace_pointer(id, new_entity)
        return unless id && new_entity && new_entity.valid?
        @cache[id.to_s] = new_entity
      end

      # Remove a single entry from the cache.
      def evict(id)
        if @cache.delete(id.to_s)
          @purged += 1
        end
      end

      # Hard reset — used by `ops.clear_model`.
      def reset
        @cache = {}
        @purged = 0
      end

      # Diagnostic — dump current cache state.
      def stats
        live = @cache.count { |_, e| e && e.valid? }
        { 
          total_tracked: @cache.size,
          live: live,
          purged_orphans: @purged
        }
      end

      private

      def scan_active_entities_for(entities, key)
        entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          if ent.get_attribute(DICT_NAME, KEY_NAME) == key
            @cache[key] = ent
            return ent
          end
        end
        nil
      end

      def scan_top_level_entities_for(entities, key)
        entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          if ent.get_attribute(DICT_NAME, KEY_NAME) == key
            @cache[key] = ent
            return ent
          end
        end
        nil
      end
    end
  end
end
