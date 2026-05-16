require_relative '../logger'

module SUMCPBridge
  module Ops
    module Query
      # =====================================================================
      # export_json — walks the model and returns a BuildingJSON-shaped state.
      # Used by `verify` (post-apply) and as a standalone tool.
      # =====================================================================
      def self.export_json(_params)
        model = Sketchup.active_model
        entities = []
        type_counts = Hash.new(0)

        model.active_entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          ai_id = ent.get_attribute("su_mcp_bridge", "ai_id")
          next unless ai_id

          type = ent.get_attribute("su_mcp_bridge", "type") || _infer_type(ent)
          type_counts[type] += 1

          bb = ent.bounds
          entry = {
            "ai_id" => ai_id,
            "guid"  => (ent.respond_to?(:guid) ? ent.guid : nil),
            "type"  => type,
            "layer" => (ent.respond_to?(:layer) && ent.layer ? ent.layer.name : nil),
            "bounds" => {
              "min" => bb.min.to_a, "max" => bb.max.to_a,
              "width" => bb.width, "depth" => bb.depth, "height" => bb.height
            },
            "volume" => begin; ent.respond_to?(:volume) ? ent.volume : 0; rescue; 0; end,
            "valid_solid" => begin; ent.respond_to?(:manifold?) ? ent.manifold? : false; rescue; false; end
          }

          # Echo back the original spec (wall_spec / openings_spec / etc.) for debugging.
          spec = ent.get_attribute("su_mcp_bridge", "wall_spec") if type == "wall"
          spec = ent.get_attribute("su_mcp_bridge", "roof_spec") if type == "roof"
          spec = ent.get_attribute("su_mcp_bridge", "component_spec") if type == "component"
          entry["spec"] = spec if spec

          entities << entry
        end

        { "entities" => entities, "total" => entities.length, "type_counts" => type_counts }
      end

      # =====================================================================
      # deep_scan — comprehensive model introspection with optional pagination
      # and inline attribute dictionary embedding.
      #
      # Params:
      #   limit        (int)  — max entities to return per page (default: all)
      #   offset       (int)  — skip first N entities (default: 0)
      #   include_attrs (bool) — embed ALL attribute dictionaries on each entity
      #                          under "attrs": {"bim": {...}, ...} (default: false)
      #   type_filter  (str)  — only return entities of this type ("wall", "slab"…)
      # =====================================================================
      def self.deep_scan(params)
        model    = Sketchup.active_model
        mm_to_in = 1.0 / 25.4

        limit         = params["limit"]  ? params["limit"].to_i  : nil
        offset        = params["offset"] ? params["offset"].to_i : 0
        include_attrs = params["include_attrs"] == true || params["include_attrs"] == "true"
        type_filter   = params["type_filter"]

        # 1. Walk all ComponentDefinitions (unaffected by pagination)
        definitions = []
        model.definitions.each do |defn|
          next if defn.image? || defn.group?
          face_count = defn.entities.grep(Sketchup::Face).length
          edge_count = defn.entities.grep(Sketchup::Edge).length
          definitions << {
            "name"            => defn.name,
            "instances_count" => defn.instances.length,
            "faces"           => face_count,
            "edges"           => edge_count,
            "is_solid"        => (face_count > 0 rescue false),
            "description"     => defn.description
          }
        end

        # 2. Collect all AI-tracked entities first (for accurate total_count)
        all_tracked = []
        model.active_entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          ai_id = ent.get_attribute("su_mcp_bridge", "ai_id")
          next unless ai_id
          next if type_filter && ent.get_attribute("su_mcp_bridge", "type") != type_filter
          all_tracked << ent
        end

        total_count = all_tracked.length
        page_entities = all_tracked[offset, limit || total_count] || []

        # 3. Build entity records for the current page
        entities = []
        total_faces = 0
        total_edges = 0
        solids = 0
        non_solids = 0

        page_entities.each do |ent|
          ai_id = ent.get_attribute("su_mcp_bridge", "ai_id")
          type  = ent.get_attribute("su_mcp_bridge", "type") || _infer_type(ent)
          bb    = ent.bounds

          fc = 0; ec = 0
          if ent.respond_to?(:entities)
            fc = ent.entities.grep(Sketchup::Face).length
            ec = ent.entities.grep(Sketchup::Edge).length
          end
          total_faces += fc
          total_edges += ec

          is_solid = begin; ent.respond_to?(:manifold?) ? ent.manifold? : false; rescue; false; end
          is_solid ? (solids += 1) : (non_solids += 1)

          vol = begin; ent.respond_to?(:volume) ? ent.volume : 0; rescue; 0; end

          mat_name = nil
          if ent.respond_to?(:material) && ent.material
            mat_name = ent.material.display_name
          end

          entry = {
            "ai_id"      => ai_id,
            "guid"       => (ent.respond_to?(:guid) ? ent.guid : nil),
            "type"       => type,
            "layer"      => (ent.respond_to?(:layer) && ent.layer ? ent.layer.name : nil),
            "material"   => mat_name,
            "bounds_mm"  => {
              "min" => bb.min.to_a.map { |v| (v / mm_to_in).round(3) },
              "max" => bb.max.to_a.map { |v| (v / mm_to_in).round(3) }
            },
            "volume_mm3" => (vol / (mm_to_in**3)).round(3),
            "face_count" => fc,
            "edge_count" => ec,
            "is_solid"   => is_solid
          }

          # Attach SAIE specs
          if type == "wall"
            spec = ent.get_attribute("su_mcp_bridge", "wall_spec")
            entry["spec"] = spec if spec
          end
          if type == "roof"
            spec = ent.get_attribute("su_mcp_bridge", "roof_spec")
            entry["spec"] = spec if spec
          end
          if type == "component"
            spec = ent.get_attribute("su_mcp_bridge", "component_spec")
            entry["spec"] = spec if spec
          end
          openings = ent.get_attribute("su_mcp_bridge", "openings_spec")
          entry["openings"] = openings if openings && !openings.empty?

          tags = SUMCPBridge::AI_ID.get_tags(ent)
          entry["tags"] = tags if tags && !tags.empty?

          # Inline attribute dictionaries — eliminates N+1 query.attr.get calls
          if include_attrs
            attrs = {}
            dicts = ent.attribute_dictionaries
            if dicts
              dicts.each do |dict|
                next if dict.name == "su_mcp_bridge"  # internal — omit
                data = {}
                dict.each_pair { |k, v| data[k] = v }
                attrs[dict.name] = data
              end
            end
            entry["attrs"] = attrs unless attrs.empty?
          end

          entities << entry
        end

        has_more = limit ? (offset + page_entities.length < total_count) : false

        {
          "definitions" => definitions,
          "entities"    => entities,
          "summary"     => {
            "total_entities"    => entities.length,
            "total_count"       => total_count,
            "total_faces"       => total_faces,
            "total_edges"       => total_edges,
            "definitions_count" => definitions.length,
            "solids_count"      => solids,
            "non_solids_count"  => non_solids
          },
          "page" => {
            "offset"   => offset,
            "limit"    => limit,
            "returned" => page_entities.length,
            "total"    => total_count,
            "has_more" => has_more
          }
        }
      rescue => e
        Logger.error("query.deep_scan failed: #{e.message}")
        { "error" => "deep_scan failed: #{e.message}" }
      end

      # =====================================================================
      # scene_summary — token-efficient (~200 token) digest of the model.
      # =====================================================================
      def self.scene_summary(_params)
        model = Sketchup.active_model
        bb = model.bounds

        type_counts = Hash.new(0)
        model.active_entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          next unless ent.get_attribute("su_mcp_bridge", "ai_id")
          type = ent.get_attribute("su_mcp_bridge", "type") || _infer_type(ent)
          type_counts[type] += 1
        end

        {
          "title" => model.title,
          "modified" => model.modified?,
          "bounds" => {
            "min_in" => bb.min.to_a, "max_in" => bb.max.to_a,
            "width_in" => bb.width, "depth_in" => bb.depth, "height_in" => bb.height
          },
          "ai_entity_counts" => type_counts,
          "ai_entity_total"  => type_counts.values.sum,
          "raw_entity_count" => model.entities.length,
          "layer_names"      => model.layers.map(&:name),
          "material_names"   => model.materials.map(&:display_name)
        }
      end

      # =====================================================================
      # entity — full record for a single ai_id.
      # =====================================================================
      def self.entity(params)
        ai_id = params["ai_id"]
        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Entity not found: #{ai_id}" } unless ent

        bb = ent.bounds
        {
          "ai_id" => ai_id,
          "guid"  => ent.respond_to?(:guid) ? ent.guid : nil,
          "type"  => ent.get_attribute("su_mcp_bridge", "type") || _infer_type(ent),
          "layer" => ent.respond_to?(:layer) && ent.layer ? ent.layer.name : nil,
          "bounds" => {
            "min" => bb.min.to_a, "max" => bb.max.to_a
          },
          "wall_spec"     => ent.get_attribute("su_mcp_bridge", "wall_spec"),
          "openings_spec" => ent.get_attribute("su_mcp_bridge", "openings_spec"),
          "roof_spec"     => ent.get_attribute("su_mcp_bridge", "roof_spec"),
          "component_spec" => ent.get_attribute("su_mcp_bridge", "component_spec")
        }
      end

      # =====================================================================
      # verify — does the model contain every expected ai_id?
      # =====================================================================
      def self.verify(params)
        expected = params["expected_ids"] || []
        model = Sketchup.active_model

        present = {}
        model.active_entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          ai_id = ent.get_attribute("su_mcp_bridge", "ai_id")
          present[ai_id] = ent.respond_to?(:guid) ? ent.guid : nil if ai_id
          
          # Openings exist as metadata on the wall, not as standalone entities
          ops = ent.get_attribute("su_mcp_bridge", "openings_spec") || []
          ops.each do |op|
            op_id = op["ai_id"]
            present[op_id] = "opening_on_#{ai_id}" if op_id
          end
        end

        found   = []
        missing = []
        expected.each { |eid| present.key?(eid) ? found << eid : missing << eid }
        orphans = present.keys.reject { |mid| expected.include?(mid) }

        {
          "found"        => found,
          "missing"      => missing,
          "orphans"      => orphans,
          "divergences"  => missing.length + orphans.length,
          "status"       => (missing.empty? && orphans.empty?) ? "clean" : "diverged"
        }
      end

      # =====================================================================
      # delete — generic delete by ai_id (used by ops.delete RPC).
      # =====================================================================
      def self.delete(params)
        ai_id = params["ai_id"]
        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Entity not found: #{ai_id}" } unless ent

        model = Sketchup.active_model
        model.start_operation("Delete #{ai_id}", true)
        ent.erase!
        model.commit_operation
        SUMCPBridge::AI_ID.evict(ai_id)
        { "ai_id" => ai_id, "status" => "deleted" }
      end

      # =====================================================================
      # set_material — apply hex color to a single entity by ai_id.
      # =====================================================================
      def self.set_material(params)
        ai_id = params["ai_id"]
        color = params["color_hex"]
        return { "error" => "ai_id is required" } unless ai_id
        return { "error" => "color_hex is required" } unless color

        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Entity not found: #{ai_id}" } unless ent

        model = Sketchup.active_model
        mat_name = "AI_#{color}"
        mat = model.materials[mat_name] || model.materials.add(mat_name)
        r = color[0..1].to_i(16)
        g = color[2..3].to_i(16)
        b = color[4..5].to_i(16)
        mat.color = Sketchup::Color.new(r, g, b)
        ent.material = mat

        { "ai_id" => ai_id, "material" => mat_name, "status" => "applied" }
      end

      # ---------------------------------------------------------------------
      # Best-effort type inference for entities created before the type
      # attribute was being written.
      def self._infer_type(ent)
        case ent
        when Sketchup::Group
          "group"
        when Sketchup::ComponentInstance
          "component"
        else
          ent.class.name.split('::').last.downcase
        end
      end
    end
  end
end
