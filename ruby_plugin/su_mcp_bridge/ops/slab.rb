module SUMCPBridge
  module Ops
    module Slab
      def self.create(params)
        model = Sketchup.active_model
        ents  = model.active_entities
        
        ai_id = params["ai_id"] || params["id"]
        upserted = false
        unless ai_id && !ai_id.empty?
          ai_id = SUMCPBridge::AI_ID.auto_name(:slab, params["polygon"]&.first)
        else
          existing = SUMCPBridge::AI_ID.find(ai_id)
          if existing && existing.valid?
            existing.erase!
            SUMCPBridge::AI_ID.evict(ai_id)
            upserted = true
          end
        end
        tags = params["tags"] || []
        polygon = params["polygon"]  # [[x,y], [x,y], ...] in mm
        thickness = (params["thickness_mm"] || 150).to_f / 25.4
        top_or_bottom = params["top_or_bottom"] || "top"
        base_z = (params["base_z_mm"] || 0).to_f / 25.4
        
        # Convert polygon points from mm to inches.
        # Accept both 2-element [x, y] and (legacy) 3-element [x, y, z] arrays.
        # Z is ALWAYS taken from base_z_mm — any per-point Z is intentionally
        # ignored so callers don't accidentally bake a wrong Z into the face.
        return { "error" => "Need at least 3 points for slab" } if polygon.length < 3

        pts = polygon.map { |pt| Geom::Point3d.new(pt[0].to_f / 25.4, pt[1].to_f / 25.4, base_z) }

        model.start_operation("Create slab #{ai_id}", true)
        group = ents.add_group
        begin
          face = group.entities.add_face(pts)
          raise "add_face returned nil — polygon may be degenerate" unless face

          if top_or_bottom == "top"
            face.reverse! if face.normal.z < 0
            face.pushpull(-thickness)   # extrude downward
          else
            face.reverse! if face.normal.z > 0
            face.pushpull(thickness)    # extrude upward
          end
        rescue => e
          model.abort_operation
          return { "error" => "slab.create failed: #{e.message}" }
        end

        model.commit_operation
        SUMCPBridge::AI_ID.set(group, ai_id, tags: tags)

        { "ai_id" => ai_id, "guid" => group.guid, "status" => upserted ? "upserted" : "created" }
      end

      def self.delete(params)
        ai_id = params["ai_id"] || params["id"]
        ent = SUMCPBridge::AI_ID.resolve(ai_id)
        return { "error" => "Slab not found: #{ai_id}" } unless ent && ent.valid?
        ent.erase!
        SUMCPBridge::AI_ID.evict(ai_id)
        { "ai_id" => ai_id, "status" => "deleted" }
      end
    end
  end
end
