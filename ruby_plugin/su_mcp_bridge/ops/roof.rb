require_relative '../logger'

module SUMCPBridge
  module Ops
    module Roof
      MM_TO_IN = 1.0 / 25.4

      # Build a roof from a footprint polygon + kind.
      # Supported kinds:
      #   * "flat"  — extruded prism, thickness = ridge_height_mm.
      #   * "shed"  — single-pitch ramp from one edge to its opposite.
      #   * "gable" — symmetric ridge running along the polygon's longest axis.
      #   * "hip"   — pyramidal: every edge slopes up to the geometric centroid.
      #
      # Returns the standard envelope { ai_id, guid, status, kind }.
      def self.create(params)
        model = Sketchup.active_model
        ents  = model.active_entities

        ai_id    = params["ai_id"] || params["id"]
        upserted = false
        unless ai_id && !ai_id.empty?
          ai_id = SUMCPBridge::AI_ID.auto_name(:roof, params["footprint"]&.first)
        else
          existing = SUMCPBridge::AI_ID.find(ai_id)
          if existing && existing.valid?
            existing.erase!
            SUMCPBridge::AI_ID.evict(ai_id)
            upserted = true
          end
        end
        tags    = params["tags"] || []
        kind    = (params["kind"] || "gable").to_s
        pitch_d = (params["pitch_deg"] || 30.0).to_f
        eave_in = ((params["eave_overhang_mm"] || 0.0).to_f) * MM_TO_IN
        ridge_h = ((params["ridge_height_mm"] || 0.0).to_f) * MM_TO_IN
        base_z  = ((params["base_z_mm"] || 0.0).to_f) * MM_TO_IN

        footprint_mm = params["footprint"] || []
        return { "error" => "footprint must have at least 3 points" } if footprint_mm.length < 3

        # Convert to inches and apply eave overhang (outward offset is approximate;
        # for v2 we keep the simple "use footprint as-is" path. AI can supply an
        # already-overhung footprint if it wants accuracy.)
        footprint = footprint_mm.map { |p| Geom::Point3d.new(p[0] * MM_TO_IN, p[1] * MM_TO_IN, base_z) }

        model.start_operation("Create roof #{ai_id}", true)
        group = ents.add_group
        ge = group.entities

        case kind
        when "flat"
          _build_flat(ge, footprint, [ridge_h, 1.0].max)
        when "shed"
          _build_shed(ge, footprint, pitch_d)
        when "gable"
          _build_gable(ge, footprint, pitch_d, ridge_h)
        when "hip"
          _build_hip(ge, footprint, pitch_d, ridge_h)
        else
          model.abort_operation
          return { "error" => "Unknown roof kind: #{kind}" }
        end

        SUMCPBridge::AI_ID.set(group, ai_id, tags: tags)
        group.set_attribute("su_mcp_bridge", "type", "roof")
        group.set_attribute("su_mcp_bridge", "roof_spec", params)

        model.commit_operation
        { "ai_id" => ai_id, "guid" => group.guid, "kind" => kind, "status" => upserted ? "upserted" : "created" }
      rescue => e
        model.abort_operation rescue nil
        SUMCPBridge::Logger.error("ops.roof.create failed: #{e.message}")
        { "error" => "roof.create failed: #{e.message}" }
      end

      def self.delete(params)
        ai_id = params["ai_id"]
        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Roof not found: #{ai_id}" } unless ent
        model = Sketchup.active_model
        model.start_operation("Delete roof #{ai_id}", true)
        ent.erase!
        model.commit_operation
        SUMCPBridge::AI_ID.evict(ai_id)
        { "ai_id" => ai_id, "status" => "deleted" }
      end

      # ---------------------------------------------------------------------
      # Builders
      # ---------------------------------------------------------------------

      def self._build_flat(ents, footprint, height_in)
        face = ents.add_face(footprint)
        face.reverse! if face.normal.z < 0
        face.pushpull(height_in)
      end

      def self._build_shed(ents, footprint, pitch_deg)
        # Single-pitch ramp. Long axis horizontal, short axis tilted.
        # Approximation: extrude flat then rotate top edge.
        # For v2 we use a simpler approach: lift one half of footprint vertices.
        # Find the polygon's bbox.
        xs = footprint.map(&:x); ys = footprint.map(&:y)
        cy_mid = (ys.min + ys.max) / 2.0
        depth = ys.max - ys.min
        rise = depth * Math.tan(pitch_deg * Math::PI / 180.0)

        lifted = footprint.map do |p|
          z = p.y > cy_mid ? p.z + rise : p.z
          Geom::Point3d.new(p.x, p.y, z)
        end
        face = ents.add_face(lifted)
        face.reverse! if face.normal.z < 0
        # Cap downward to make it solid.
        face.pushpull(-(0.25))  # 1/4 inch sheathing thickness; visible volume.
      end

      def self._build_gable(ents, footprint, pitch_deg, ridge_h_in)
        # Approximate gable: ridge along the polygon's long axis, two sloped faces.
        xs = footprint.map(&:x); ys = footprint.map(&:y)
        x_min, x_max = xs.min, xs.max
        y_min, y_max = ys.min, ys.max
        width  = x_max - x_min
        depth  = y_max - y_min
        ridge_h = ridge_h_in
        ridge_h = (depth.abs / 2.0) * Math.tan(pitch_deg * Math::PI / 180.0) if ridge_h <= 0

        # Decide ridge axis: along the longer span.
        ridge_axis_is_x = width >= depth

        # Build the two sloped triangles + two end gable triangles.
        if ridge_axis_is_x
          y_mid = (y_min + y_max) / 2.0
          ridge_start = Geom::Point3d.new(x_min, y_mid, footprint.first.z + ridge_h)
          ridge_end   = Geom::Point3d.new(x_max, y_mid, footprint.first.z + ridge_h)

          # Two sloped roof faces
          ents.add_face(
            Geom::Point3d.new(x_min, y_min, footprint.first.z),
            Geom::Point3d.new(x_max, y_min, footprint.first.z),
            ridge_end, ridge_start
          )
          ents.add_face(
            Geom::Point3d.new(x_max, y_max, footprint.first.z),
            Geom::Point3d.new(x_min, y_max, footprint.first.z),
            ridge_start, ridge_end
          )
          # End triangles (gables)
          ents.add_face(
            Geom::Point3d.new(x_min, y_min, footprint.first.z),
            ridge_start,
            Geom::Point3d.new(x_min, y_max, footprint.first.z)
          )
          ents.add_face(
            Geom::Point3d.new(x_max, y_min, footprint.first.z),
            Geom::Point3d.new(x_max, y_max, footprint.first.z),
            ridge_end
          )
        else
          x_mid = (x_min + x_max) / 2.0
          ridge_start = Geom::Point3d.new(x_mid, y_min, footprint.first.z + ridge_h)
          ridge_end   = Geom::Point3d.new(x_mid, y_max, footprint.first.z + ridge_h)
          ents.add_face(
            Geom::Point3d.new(x_min, y_min, footprint.first.z),
            Geom::Point3d.new(x_min, y_max, footprint.first.z),
            ridge_end, ridge_start
          )
          ents.add_face(
            Geom::Point3d.new(x_max, y_max, footprint.first.z),
            Geom::Point3d.new(x_max, y_min, footprint.first.z),
            ridge_start, ridge_end
          )
          ents.add_face(
            Geom::Point3d.new(x_min, y_min, footprint.first.z),
            ridge_start,
            Geom::Point3d.new(x_max, y_min, footprint.first.z)
          )
          ents.add_face(
            Geom::Point3d.new(x_min, y_max, footprint.first.z),
            Geom::Point3d.new(x_max, y_max, footprint.first.z),
            ridge_end
          )
        end
      end

      def self._build_hip(ents, footprint, pitch_deg, ridge_h_in)
        # Pyramidal-ish: connect every edge to the centroid lifted by ridge_h.
        xs = footprint.map(&:x); ys = footprint.map(&:y)
        cx = xs.sum / xs.size.to_f
        cy = ys.sum / ys.size.to_f
        ridge_h = ridge_h_in
        ridge_h = ((xs.max - xs.min) + (ys.max - ys.min)) / 4.0 * Math.tan(pitch_deg * Math::PI / 180.0) if ridge_h <= 0
        apex = Geom::Point3d.new(cx, cy, footprint.first.z + ridge_h)

        n = footprint.length
        n.times do |i|
          a = footprint[i]
          b = footprint[(i + 1) % n]
          ents.add_face(a, b, apex)
        end
      end
    end
  end
end
