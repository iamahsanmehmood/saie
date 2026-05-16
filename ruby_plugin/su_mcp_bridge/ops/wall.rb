require_relative '../logger'

module SUMCPBridge
  module Ops
    module Wall
      # Conversion factor (1 inch = 25.4 mm). Centralized so we don't sprinkle
      # the literal across the file.
      MM_TO_IN = 1.0 / 25.4

      # ----------------------------------------------------------------------
      # CREATE
      # ----------------------------------------------------------------------
      def self.create(params)
        model = Sketchup.active_model
        ents  = model.active_entities

        coords = _read_centerline(params)
        return { "error" => "zero-length wall" } if coords[:len] < 0.001

        ai_id = params["ai_id"] || params["id"]
        upserted = false
        unless ai_id && !ai_id.empty?
          cl_mm = params["centerline"] ? params["centerline"].first : [params["start_x"].to_f * 25.4, params["start_y"].to_f * 25.4]
          ai_id = SUMCPBridge::AI_ID.auto_name(:wall, cl_mm)
        else
          existing = SUMCPBridge::AI_ID.find(ai_id)
          if existing && existing.valid?
            existing.erase!
            SUMCPBridge::AI_ID.evict(ai_id)
            upserted = true
          end
        end
        level = params["level"] || "GF"
        tags  = params["tags"] || []

        group = _build_wall_group(ents, coords)
        _assign_layer(group, model, level)

        SUMCPBridge::AI_ID.set(group, ai_id, tags: tags)

        # Persist the creation params on the group so `opening.modify` (or any
        # future "rebuild this wall" op) can reconstruct the wall verbatim.
        # The attribute survives boolean subtract because SketchUp copies the
        # attribute dictionary onto the surviving group.
        group.set_attribute("su_mcp_bridge", "wall_spec", params)
        group.set_attribute("su_mcp_bridge", "type", "wall")

        SUMCPBridge::Logger.debug("ops.wall.create #{ai_id} -> guid=#{group.guid} (#{upserted ? 'upserted' : 'created'})")

        {
          "ai_id"  => ai_id,
          "guid"   => group.guid,
          "status" => upserted ? "upserted" : "created",
          "bounds" => {
            "min" => group.bounds.min.to_a.map { |v| (v * 25.4).round(3) },
            "max" => group.bounds.max.to_a.map { |v| (v * 25.4).round(3) }
          }
        }
      end

      # ----------------------------------------------------------------------
      # MODIFY (delete + recreate, preserving ai_id and any opening cuts on it)
      # ----------------------------------------------------------------------
      #
      # SketchUp does not let you reliably edit a wall solid in place after
      # boolean ops. Strategy: erase the wall group AND every opening that
      # cuts it from the AI's perspective, then rebuild the wall from the new
      # parameters. The CALLER (apply.py / sync engine) is responsible for
      # re-cutting the openings on the new wall.
      def self.modify(params)
        ai_id = params["ai_id"] || params["id"]
        return { "error" => "ai_id is required for ops.wall.modify" } unless ai_id

        model = Sketchup.active_model
        existing = SUMCPBridge::AI_ID.find(ai_id)

        if existing && existing.valid?
          model.start_operation("Modify wall #{ai_id}", true)
          existing.erase!
          model.commit_operation
          SUMCPBridge::AI_ID.evict(ai_id)
        else
          SUMCPBridge::Logger.warn("ops.wall.modify: existing wall #{ai_id} not found; creating fresh")
        end

        create(params)
      end

      # ----------------------------------------------------------------------
      # DELETE
      # ----------------------------------------------------------------------
      def self.delete(params)
        ai_id = params["ai_id"] || params["id"]
        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Wall not found: #{ai_id}" } unless ent

        model = Sketchup.active_model
        model.start_operation("Delete wall #{ai_id}", true)
        ent.erase!
        model.commit_operation
        SUMCPBridge::AI_ID.evict(ai_id)

        { "ai_id" => ai_id, "status" => "deleted" }
      end

      # ======================================================================
      # Helpers
      # ======================================================================

      # Read centerline + thickness + height from either v1 (inches, start_x/end_x)
      # or v2 (mm, centerline:[[x,y],[x,y]]) parameter shape. Returns inches.
      def self._read_centerline(params)
        if params["centerline"]
          cl = params["centerline"]
          x1 = cl[0][0].to_f * MM_TO_IN
          y1 = cl[0][1].to_f * MM_TO_IN
          x2 = cl[1][0].to_f * MM_TO_IN
          y2 = cl[1][1].to_f * MM_TO_IN
          thick = params["thickness_mm"].to_f * MM_TO_IN
          height = params["height_mm"].to_f * MM_TO_IN
        else
          x1 = params["start_x"].to_f
          y1 = params["start_y"].to_f
          x2 = params["end_x"].to_f
          y2 = params["end_y"].to_f
          thick = params["thickness"].to_f
          height = params["height"].to_f
        end

        dx = x2 - x1
        dy = y2 - y1
        len = Math.sqrt(dx*dx + dy*dy)

        {
          x1: x1, y1: y1, x2: x2, y2: y2,
          dx: dx, dy: dy,
          len: len,
          thick: thick, height: height
        }
      end

      # Build the 4 footprint corners + extrude.
      def self._build_wall_group(ents, c)
        # Perpendicular offset (proven v1 math): rotate (dx,dy)/len by +90deg.
        len = c[:len]
        px = (-c[:dy] / len) * (c[:thick] / 2.0)
        py = ( c[:dx] / len) * (c[:thick] / 2.0)

        p1 = Geom::Point3d.new(c[:x1] + px, c[:y1] + py, 0)
        p2 = Geom::Point3d.new(c[:x2] + px, c[:y2] + py, 0)
        p3 = Geom::Point3d.new(c[:x2] - px, c[:y2] - py, 0)
        p4 = Geom::Point3d.new(c[:x1] - px, c[:y1] - py, 0)

        group = ents.add_group
        face = group.entities.add_face(p1, p2, p3, p4)
        face.reverse! if face.normal.z < 0
        face.pushpull(c[:height])
        group
      end

      def self._assign_layer(group, model, level_name)
        tag = nil
        begin
          tag = model.layers.add(level_name)
        rescue
          tag = model.layers[level_name]
        end
        group.layer = tag if tag
      end
    end
  end
end
