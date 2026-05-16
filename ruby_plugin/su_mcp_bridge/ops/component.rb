require_relative '../logger'

module SUMCPBridge
  module Ops
    # Real SketchUp components (ComponentDefinition + ComponentInstance).
    # Doors and windows should be placed as components attached to openings,
    # not as boolean voids — this is what gives realistic 3D models.
    module Component
      MM_TO_IN = 1.0 / 25.4
      COMP_Z_AXIS = Geom::Vector3d.new(0, 0, 1).freeze unless const_defined?(:COMP_Z_AXIS)

      # Place a component instance from a .skp file or a built-in primitive recipe.
      # Params:
      #   ai_id            (str)            : stable identifier
      #   definition_path  (str, optional)  : absolute path to .skp file
      #   recipe           (str, optional)  : "door"|"window" — built-in stub geometry
      #   position_mm      ([x,y,z])        : insertion point in mm
      #   rotation_deg     (float, default 0) : rotation around Z
      #   scale            ([sx,sy,sz], default [1,1,1]) : per-axis scale
      #   attached_to      (str, optional)  : opening ai_id; we'll snap to that opening
      #   width_mm/height_mm/thickness_mm   : recipe sizing
      def self.place(params)
        model = Sketchup.active_model
        ai_id = params["ai_id"] || params["id"]
        unless ai_id && !ai_id.empty?
          ai_id = SUMCPBridge::AI_ID.auto_name(:component, params["position_mm"])
        end
        tags = params["tags"] || []

        defn = nil
        if params["definition_path"] && File.exist?(params["definition_path"])
          defn = model.definitions.load(params["definition_path"])
        elsif params["recipe"]
          defn = _ensure_recipe_definition(model, params)
        end

        return { "error" => "No definition_path or recipe supplied for component" } unless defn

        pos_mm   = params["position_mm"] || [0, 0, 0]
        rot_deg  = (params["rotation_deg"] || 0).to_f
        scale    = params["scale"] || [1.0, 1.0, 1.0]

        position = Geom::Point3d.new(
          pos_mm[0] * MM_TO_IN,
          pos_mm[1] * MM_TO_IN,
          pos_mm[2] * MM_TO_IN
        )

        # Snap to opening if requested.
        if params["attached_to"]
          snap = _opening_anchor(params["attached_to"])
          position = snap if snap
        end

        tr = Geom::Transformation.translation(position)
        tr = tr * Geom::Transformation.rotation(position, COMP_Z_AXIS, rot_deg.degrees)
        tr = tr * Geom::Transformation.scaling(scale[0], scale[1], scale[2])

        model.start_operation("Place component #{ai_id}", true)
        instance = model.active_entities.add_instance(defn, tr)
        SUMCPBridge::AI_ID.set(instance, ai_id, tags: tags)
        instance.set_attribute("su_mcp_bridge", "type", "component")
        instance.set_attribute("su_mcp_bridge", "component_spec", params)
        model.commit_operation

        { "ai_id" => ai_id, "guid" => instance.guid, "definition" => defn.name, "status" => "placed" }
      rescue => e
        model.abort_operation rescue nil
        SUMCPBridge::Logger.error("ops.component.place failed: #{e.message}")
        { "error" => "component.place failed: #{e.message}" }
      end

      def self.delete(params)
        ai_id = params["ai_id"]
        ent = SUMCPBridge::AI_ID.find(ai_id)
        return { "error" => "Component not found: #{ai_id}" } unless ent
        model = Sketchup.active_model
        model.start_operation("Delete component #{ai_id}", true)
        ent.erase!
        model.commit_operation
        SUMCPBridge::AI_ID.evict(ai_id)
        { "ai_id" => ai_id, "status" => "deleted" }
      end

      # ---------------------------------------------------------------------
      # Built-in recipe definitions (door, window) so the AI doesn't need
      # external .skp files for basic openings.
      # ---------------------------------------------------------------------

      def self._ensure_recipe_definition(model, params)
        recipe = params["recipe"].to_s
        w_in = (params["width_mm"]  || 900).to_f * MM_TO_IN
        h_in = (params["height_mm"] || 2100).to_f * MM_TO_IN
        t_in = (params["thickness_mm"] || 40).to_f * MM_TO_IN
        name = "AI_RECIPE_V3_#{recipe}_#{w_in.round(2)}x#{h_in.round(2)}x#{t_in.round(2)}"

        existing = model.definitions[name]
        return existing if existing

        defn = model.definitions.add(name)
        ents = defn.entities

        case recipe
        when "door"
          # Simple open door panel (hinged at origin, rotated 60 deg open)
          panel_w = w_in
          panel_t = 1.5 * MM_TO_IN # 1.5 inch thick door
          group = ents.add_group
          face = group.entities.add_face(
            Geom::Point3d.new(0, 0, 0),
            Geom::Point3d.new(panel_w, 0, 0),
            Geom::Point3d.new(panel_w, panel_t, 0),
            Geom::Point3d.new(0, panel_t, 0)
          )
          face.reverse! if face.normal.z < 0
          face.pushpull(h_in)
          # rotate it open by 60 degrees around Z axis at origin
          tr = Geom::Transformation.rotation(Geom::Point3d.new(0,0,0), Geom::Vector3d.new(0,0,1), 60.degrees)
          group.transform!(tr)
          # explode to merge into component
          group.explode

        when "window"
          # Frame: a box slab with an inset rectangle to suggest glass.
          face = ents.add_face(
            Geom::Point3d.new(0,    0,    0),
            Geom::Point3d.new(w_in, 0,    0),
            Geom::Point3d.new(w_in, t_in, 0),
            Geom::Point3d.new(0,    t_in, 0)
          )
          face.reverse! if face.normal.z < 0
          face.pushpull(h_in)
          # The "glass" inset suggestion — a rectangle on the front face.
          frame_thick = 2.0 * MM_TO_IN
          inset_w = w_in - (frame_thick * 2)
          inset_h = h_in - (frame_thick * 2)
          ox = frame_thick
          oz = frame_thick
          inset_face = ents.add_face(
            Geom::Point3d.new(ox, 0, oz),
            Geom::Point3d.new(ox + inset_w, 0, oz),
            Geom::Point3d.new(ox + inset_w, 0, oz + inset_h),
            Geom::Point3d.new(ox, 0, oz + inset_h)
          )
          # Pushpull through the block to make it hollow!
          inset_face.pushpull(-t_in)
        else
          ents.add_face(
            Geom::Point3d.new(0,    0,    0),
            Geom::Point3d.new(w_in, 0,    0),
            Geom::Point3d.new(w_in, t_in, 0),
            Geom::Point3d.new(0,    t_in, 0)
          )
        end

        defn
      end

      # Compute the world-coords anchor point for an opening: bottom-center of
      # the opening, on the wall's centerline. Returns nil if not findable.
      def self._opening_anchor(opening_ai_id)
        # Walk all walls; check their openings_spec for the matching id.
        Sketchup.active_model.active_entities.each do |ent|
          next unless ent.is_a?(Sketchup::Group) && ent.valid?
          ops = ent.get_attribute("su_mcp_bridge", "openings_spec") || []
          match = ops.find { |o| o["ai_id"] == opening_ai_id }
          next unless match

          # Read wall's centerline (in inches) from its wall_spec.
          wall_spec = ent.get_attribute("su_mcp_bridge", "wall_spec")
          next unless wall_spec

          if wall_spec["centerline"]
            x1 = wall_spec["centerline"][0][0].to_f * MM_TO_IN
            y1 = wall_spec["centerline"][0][1].to_f * MM_TO_IN
            x2 = wall_spec["centerline"][1][0].to_f * MM_TO_IN
            y2 = wall_spec["centerline"][1][1].to_f * MM_TO_IN
          else
            x1 = wall_spec["start_x"].to_f
            y1 = wall_spec["start_y"].to_f
            x2 = wall_spec["end_x"].to_f
            y2 = wall_spec["end_y"].to_f
          end

          dx = x2 - x1
          dy = y2 - y1
          len = Math.sqrt(dx*dx + dy*dy)
          next if len < 0.001

          ux = dx / len
          uy = dy / len

          off = (match["offset_mm"] ? match["offset_mm"].to_f * MM_TO_IN : match["offset"].to_f)
          width = (match["width_mm"] ? match["width_mm"].to_f * MM_TO_IN : match["width"].to_f)

          # Anchor at the center of the opening along the wall.
          ax = x1 + ux * (off + width / 2.0)
          ay = y1 + uy * (off + width / 2.0)

          sill = (match["sill_mm"] ? match["sill_mm"].to_f * MM_TO_IN : (match["sill"] || 0).to_f)

          return Geom::Point3d.new(ax, ay, sill)
        end
        nil
      end
    end
  end
end
