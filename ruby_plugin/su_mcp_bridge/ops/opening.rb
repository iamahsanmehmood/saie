require_relative '../logger'

module SUMCPBridge
  module Ops
    module Opening
      MM_TO_IN = 1.0 / 25.4

      # =========================================================================
      # CUT — boolean-subtract an opening from a wall
      # =========================================================================
      #
      # Improvements over v1:
      #   * Correctly handles DIAGONAL walls. The v1 prototype used
      #     `is_y_axis = bbox.dy > bbox.dx` which collapses for diagonals.
      #     v2 derives the wall's local frame from its centerline (read from
      #     the ai_id metadata or, as a fallback, from the wall's footprint
      #     long edge), and places the cutter in that local frame via a
      #     `Geom::Transformation`.
      #   * Stores the opening's params on the wall via attributes, so
      #     `ops.opening.modify` can rebuild the wall+all-openings without
      #     extra plumbing.
      def self.cut(params)
        model = Sketchup.active_model

        ai_id      = params["ai_id"] || params["id"]
        unless ai_id && !ai_id.empty?
          ai_id = SUMCPBridge::AI_ID.auto_name(:opening)
        end
        wall_ai_id = params["wall_id"]
        return { "error" => "wall_id is required" } unless wall_ai_id

        cut_params = _read_cut_params(params)

        wall_group = SUMCPBridge::AI_ID.find(wall_ai_id)
        return { "error" => "Wall not found: #{wall_ai_id}" } unless wall_group

        # Derive the wall's local frame from its footprint (long edge of the
        # bottom face). This is robust to diagonal walls.
        frame = _wall_local_frame(wall_group)
        return { "error" => "Could not determine wall frame for #{wall_ai_id}" } unless frame

        result = _perform_cut(model, wall_group, frame, cut_params, params["generate_frame"])
        return result if result["error"]

        # Persist this opening's spec on the surviving wall group so we can
        # rebuild it later if `ops.opening.modify` is called.
        _record_opening_on_wall(result[:new_wall], ai_id, wall_ai_id, params)

        tags = params["tags"] || []
        SUMCPBridge::AI_ID.set(result[:new_wall], wall_ai_id, tags: tags)
        SUMCPBridge::AI_ID.replace_pointer(wall_ai_id, result[:new_wall])

        {
          "ai_id"       => ai_id,
          "wall_id"     => wall_ai_id,
          "result_guid" => result[:new_wall].guid,
          "status"      => "cut"
        }
      end

      # =========================================================================
      # BATCH_CUT — cut ALL openings for a wall in ONE boolean operation
      # =========================================================================
      #
      # This avoids the progressive geometry corruption caused by sequential
      # boolean subtracts on the same wall.  Instead of N subtracts, we build
      # ONE combined cutter group containing ALL N opening voids, then do a
      # SINGLE subtract.  Frames are placed AFTER the subtract succeeds.
      #
      # Params:
      #   wall_id   (str)   : ai_id of the target wall
      #   openings  (array) : list of opening specs, each with:
      #     ai_id, offset_mm, width_mm, height_mm, sill_mm, generate_frame
      def self.batch_cut(params)
        begin
          model = Sketchup.active_model

          wall_ai_id = params["wall_id"]
          return { "error" => "wall_id is required" } unless wall_ai_id

          openings = params["openings"]
          return { "error" => "openings array is required" } unless openings && openings.is_a?(Array) && !openings.empty?

          wall_group = SUMCPBridge::AI_ID.find(wall_ai_id)
          return { "error" => "Wall not found: #{wall_ai_id}" } unless wall_group

          frame = _wall_local_frame(wall_group)
          return { "error" => "Could not determine wall frame for #{wall_ai_id}" } unless frame

          # Parse all opening dimensions
          parsed = openings.map { |o| _read_cut_params(o) }

          # Build the world transform (same for all openings on this wall)
          oversize = frame[:thickness] + 10.0
          z_axis = Geom::Vector3d.new(0, 0, 1)
          local_to_world = Geom::Transformation.axes(
            frame[:origin], frame[:x_axis], frame[:y_axis], z_axis
          )
          center_shift = Geom::Transformation.translation(
            Geom::Vector3d.new(0, frame[:thickness] / 2.0, 0)
          )
          full_transform = local_to_world * center_shift

          model.start_operation("Batch cut #{openings.length} openings on #{wall_ai_id}", true)

          # Build ONE combined cutter group with ALL openings
          cutter = model.active_entities.add_group
          ce = cutter.entities

          parsed.each do |cut|
            x0 = cut[:offset]
            x1 = cut[:offset] + cut[:width]
            y0 = -oversize / 2.0
            y1 =  oversize / 2.0
            # Extend cutter 1 inch below and above to avoid coplanar face bugs
            z0 = cut[:sill] - 1.0
            z1 = cut[:sill] + cut[:height] + 1.0

            # Each opening is a separate sub-group inside the cutter
            sub = ce.add_group
            pts = [
              Geom::Point3d.new(x0, y0, z0),
              Geom::Point3d.new(x1, y0, z0),
              Geom::Point3d.new(x1, y1, z0),
              Geom::Point3d.new(x0, y1, z0)
            ]
            face = sub.entities.add_face(pts)
            face.pushpull(z1 - z0) if face
            sub.explode  # merge into parent cutter group
          end

          # Transform entire combined cutter to world coords
          cutter.transform!(full_transform)

          # SINGLE boolean subtract
          begin
            new_wall = cutter.subtract(wall_group)
            if new_wall.nil?
              model.abort_operation
              return { "error" => "Boolean subtract returned nil for #{wall_ai_id}" }
            end
          rescue => e
            model.abort_operation
            return { "error" => "Subtract failed on #{wall_ai_id}: #{e.message}" }
          end

          # Place frames for each opening AFTER the subtract succeeded
          results = []
          openings.each_with_index do |o, i|
            SUMCPBridge::Logger.debug("batch_cut processing opening #{i}: #{o.inspect}")
            ai_id = o["ai_id"] || SUMCPBridge::AI_ID.auto_name(:opening)
            gen = o["generate_frame"]

            if gen && !gen.empty?
              c_spec = parsed[i]
              SUMCPBridge::Logger.debug("c_spec for #{i} is #{c_spec.inspect}")
              cx0 = c_spec[:offset]
              cx1 = c_spec[:offset] + c_spec[:width]
              cz0 = c_spec[:sill]
              cz1 = c_spec[:sill] + c_spec[:height]
              _build_frame_in_opening(model, full_transform, cx0, cx1, cz0, cz1, frame[:thickness], gen)
            end

            SUMCPBridge::Logger.debug("Recording opening #{ai_id} on wall #{wall_ai_id}")
            _record_opening_on_wall(new_wall, ai_id, wall_ai_id, o)
            results << { "ai_id" => ai_id, "status" => "cut" }
          end

          tags = params["tags"] || []
          SUMCPBridge::AI_ID.set(new_wall, wall_ai_id, tags: tags)
          SUMCPBridge::AI_ID.replace_pointer(wall_ai_id, new_wall)

          model.commit_operation

          {
            "wall_id"  => wall_ai_id,
            "openings" => results,
            "status"   => "batch_cut",
            "count"    => results.length
          }
        rescue => e
          return { "error" => "CRASH in batch_cut: #{e.message} \n #{e.backtrace.join("\n")}" }
        end
      end

      # =========================================================================
      # MODIFY — change an opening's offset/width/height/sill
      # =========================================================================
      #
      # We don't try to reverse the boolean. Instead we read the openings list
      # off the wall's attributes, replace the entry for this opening, then
      # ask Wall to rebuild itself + Opening to re-cut all openings.
      #
      # Caller can also achieve the same effect via the sync engine (delete
      # + create); this op exists for direct AI use.
      def self.modify(params)
        ai_id = params["ai_id"] || params["id"]
        return { "error" => "ai_id is required" } unless ai_id

        model = Sketchup.active_model

        # Locate which wall this opening lives on.
        wall_ai_id = params["wall_id"]
        if wall_ai_id.nil?
          # Search all walls for an opening list containing ai_id.
          wall_ai_id = _find_wall_for_opening(model, ai_id)
          return { "error" => "Could not locate wall for opening #{ai_id}" } unless wall_ai_id
        end

        wall_group = SUMCPBridge::AI_ID.find(wall_ai_id)
        return { "error" => "Wall not found: #{wall_ai_id}" } unless wall_group

        # Read the existing wall spec + openings list from attributes.
        wall_spec = wall_group.get_attribute("su_mcp_bridge", "wall_spec")
        openings_spec = wall_group.get_attribute("su_mcp_bridge", "openings_spec") || []

        # Update or remove the opening.
        new_openings = openings_spec.reject { |o| o["ai_id"] == ai_id }

        if params["delete"] != true
          updated = openings_spec.find { |o| o["ai_id"] == ai_id } || { "ai_id" => ai_id, "wall_id" => wall_ai_id }
          %w[offset_mm width_mm height_mm sill_mm offset width height sill kind].each do |k|
            updated[k] = params[k] if params.key?(k)
          end
          new_openings << updated
        end

        # Wipe and rebuild
        model.start_operation("Modify opening #{ai_id}", true)
        wall_group.erase!
        SUMCPBridge::AI_ID.evict(wall_ai_id)
        model.commit_operation

        # Re-create wall from saved spec. wall_spec is a hash of params identical to ops.wall.create.
        return { "error" => "missing wall_spec on wall #{wall_ai_id}" } unless wall_spec
        SUMCPBridge::Ops::Wall.create(wall_spec)

        # Re-cut all openings on the rebuilt wall.
        new_openings.each { |op| cut(op) }

        { "ai_id" => ai_id, "wall_id" => wall_ai_id, "status" => params["delete"] == true ? "deleted" : "modified" }
      end

      # =========================================================================
      # DELETE — convenience wrapper around modify(delete: true)
      # =========================================================================
      def self.delete(params)
        modify(params.merge("delete" => true))
      end

      # ===========================================================================
      # Helpers
      # ===========================================================================

      def self._read_cut_params(params)
        if params["offset_mm"]
          {
            offset: params["offset_mm"].to_f * MM_TO_IN,
            width:  params["width_mm"].to_f * MM_TO_IN,
            height: params["height_mm"].to_f * MM_TO_IN,
            sill:   (params["sill_mm"] || 0).to_f * MM_TO_IN
          }
        else
          {
            offset: params["offset"].to_f,
            width:  params["width"].to_f,
            height: params["height"].to_f,
            sill:   (params["sill"] || 0).to_f
          }
        end
      end

      # Derive the wall's local 2D frame from its bottom face long edge.
      # Returns { origin: Point3d, x_axis: Vector3d (along wall length),
      #          y_axis: Vector3d (across wall thickness, in plan),
      #          length: Float (inches), thickness: Float (inches) }.
      # Robust to walls oriented along ANY direction (incl. diagonals).
      def self._wall_local_frame(wall_group)
        # Find the bottom face (z near 0, normal pointing down or up parallel to z).
        bottom_face = wall_group.entities.grep(Sketchup::Face).min_by do |f|
          f.bounds.min.z.abs + f.bounds.max.z.abs
        end
        return nil unless bottom_face

        edges = bottom_face.edges
        return nil if edges.empty?

        # Long edge = wall length axis.
        long_edge = edges.max_by { |e| e.length }
        return nil unless long_edge

        # Find a perpendicular edge (the wall thickness axis).
        long_vec = long_edge.line[1].clone.normalize
        perp_edge = edges.find do |e|
          next false if e == long_edge
          v = e.line[1].clone.normalize
          (v.dot(long_vec).abs) < 0.01
        end
        return nil unless perp_edge

        thick_vec = perp_edge.line[1].clone.normalize

        # Origin: the endpoint of long_edge that is closer to the wall start
        # (we use the lex-smallest endpoint for determinism).
        a, b = long_edge.start.position, long_edge.end.position
        origin = ([a, b].sort_by { |p| [p.x, p.y, p.z] }).first

        # Re-orient long_vec to point away from origin.
        if origin.distance(b) > origin.distance(a)
          long_vec = b - a
          long_vec.normalize!
        else
          long_vec = a - b
          long_vec.normalize!
        end

        # Ensure thick_vec points INTO the face (not away from it)
        center_test = origin.offset(long_vec, long_edge.length / 2.0).offset(thick_vec, perp_edge.length / 2.0)
        if bottom_face.classify_point(center_test) == Sketchup::Face::PointOutside
          thick_vec.reverse!
        end

        {
          origin: origin,
          x_axis: long_vec,
          y_axis: thick_vec,
          length: long_edge.length,
          thickness: perp_edge.length
        }
      end

      # Build a cutter box in the wall's local frame, transform it to world,
      # subtract from the wall.
      #
      # If generate_frame is supplied (\"door\" or \"window\"), we ALSO build the
      # frame geometry using the EXACT SAME local coordinates and transform.
      # This is Solution B from ISSUES.md: the frame is built in the wall's
      # own coordinate space, mathematically guaranteeing zero misalignment.
      def self._perform_cut(model, wall_group, frame, cut, generate_frame = nil)
        oversize = frame[:thickness] + 10.0  # cutter extends past wall on both sides

        # In LOCAL coords: x = along wall, y = across wall (thickness), z = vertical.
        # Cutter spans x:[offset, offset+width], y:[-oversize/2, +oversize/2], z:[sill, sill+height]
        x0 = cut[:offset]
        x1 = cut[:offset] + cut[:width]
        y0 = -oversize / 2.0
        y1 =  oversize / 2.0
        z0 = cut[:sill]
        z1 = cut[:sill] + cut[:height]

        # World transform: rotate local frame so x_axis -> world frame x_axis at origin.
        z_axis = Geom::Vector3d.new(0, 0, 1)
        local_to_world = Geom::Transformation.axes(
          frame[:origin], frame[:x_axis], frame[:y_axis], z_axis
        )
        # Shift origin from corner to wall-thickness centerline so y=0 = wall center.
        center_shift = Geom::Transformation.translation(
          Geom::Vector3d.new(0, frame[:thickness] / 2.0, 0)
        )

        model.start_operation("Cut opening", true)

        cutter = model.active_entities.add_group
        ce = cutter.entities

        # Build cutter in local coords
        pts = [
          Geom::Point3d.new(x0, y0, z0),
          Geom::Point3d.new(x1, y0, z0),
          Geom::Point3d.new(x1, y1, z0),
          Geom::Point3d.new(x0, y1, z0)
        ]
        face = ce.add_face(pts)
        face.pushpull(z1 - z0)

        # Transform cutter from local frame to world frame.
        cutter.transform!(local_to_world * center_shift)

        begin
          new_wall = cutter.subtract(wall_group)
          if new_wall.nil?
            model.abort_operation
            return { "error" => "Boolean subtract returned nil; cutter may be outside wall." }
          end

          # ---------------------------------------------------------------
          # Solution B: Generate frame geometry IN the wall's local space
          # ---------------------------------------------------------------
          frame_group = nil
          if generate_frame && !generate_frame.empty?
            frame_group = _build_frame_in_opening(
              model, local_to_world * center_shift,
              x0, x1, z0, z1,
              frame[:thickness],
              generate_frame
            )
          end

          model.commit_operation
          result = { new_wall: new_wall }
          result[:frame_group] = frame_group if frame_group
          result
        rescue => e
          model.abort_operation
          SUMCPBridge::Logger.error("opening.cut subtract failed: #{e.message}")
          { "error" => "Subtract failed: #{e.message}" }
        end
      end

      # Build a door or window frame directly in the opening void.
      # Uses the EXACT same local-to-world transform as the cutter,
      # so alignment is mathematically guaranteed.
      #
      # frame_t = wall thickness (inches)
      # kind    = "door" or "window"
      def self._build_frame_in_opening(model, local_to_world, x0, x1, z0, z1, frame_t, kind)
        group = model.active_entities.add_group
        ge = group.entities

        w = x1 - x0           # opening width
        h = z1 - z0           # opening height
        wt = frame_t           # wall thickness (= frame depth)

        case kind
        when "door"
          # Door frame: U-shaped frame (two jambs + header) with a panel
          ft = 2.0 / 25.4     # frame member thickness: 50mm (~2 inches)

          # Left jamb
          _add_local_box(ge, x0, -wt/2.0, z0,  x0 + ft, wt/2.0, z1)
          # Right jamb
          _add_local_box(ge, x1 - ft, -wt/2.0, z0,  x1, wt/2.0, z1)
          # Header
          _add_local_box(ge, x0, -wt/2.0, z1 - ft,  x1, wt/2.0, z1)

          # Door panel (thin slab, hinged at left, rotated 30° open)
          panel_t = 1.5 / 25.4   # 38mm door panel
          panel_group = ge.add_group
          pe = panel_group.entities
          # Build panel flat along x-axis at the front face of the opening
          pf = pe.add_face(
            Geom::Point3d.new(0, -panel_t/2.0, 0),
            Geom::Point3d.new(w - 2*ft, -panel_t/2.0, 0),
            Geom::Point3d.new(w - 2*ft, panel_t/2.0, 0),
            Geom::Point3d.new(0, panel_t/2.0, 0)
          )
          pf.reverse! if pf.normal.z < 0
          pf.pushpull(h - ft)
          # Move panel to left jamb inner edge
          panel_group.transform!(Geom::Transformation.translation(
            Geom::Vector3d.new(x0 + ft, 0, z0)
          ))
          # Rotate panel 30° open around the left hinge edge (Z axis at left jamb)
          hinge_pt = Geom::Point3d.new(x0 + ft, 0, 0)
          panel_group.transform!(Geom::Transformation.rotation(
            hinge_pt, Geom::Vector3d.new(0, 0, 1), 30.degrees
          ))

        when "window"
          # Window frame: full rectangle frame + glass pane
          ft = 2.0 / 25.4     # frame member thickness: 50mm

          # Four frame members
          # Bottom rail
          _add_local_box(ge, x0, -wt/2.0, z0,  x1, wt/2.0, z0 + ft)
          # Top rail
          _add_local_box(ge, x0, -wt/2.0, z1 - ft,  x1, wt/2.0, z1)
          # Left stile
          _add_local_box(ge, x0, -wt/2.0, z0 + ft,  x0 + ft, wt/2.0, z1 - ft)
          # Right stile
          _add_local_box(ge, x1 - ft, -wt/2.0, z0 + ft,  x1, wt/2.0, z1 - ft)

          # Glass pane (very thin, centered in frame depth)
          glass_t = 0.25 / 25.4   # ~6mm glass
          _add_local_box(ge,
            x0 + ft, -glass_t/2.0, z0 + ft,
            x1 - ft, glass_t/2.0, z1 - ft
          )
        end

        # Transform the entire frame assembly from local to world coords
        group.transform!(local_to_world)

        group
      rescue => e
        SUMCPBridge::Logger.error("_build_frame_in_opening failed: #{e.message}")
        nil
      end

      # Helper: add an axis-aligned box in LOCAL coordinates to the given entities.
      def self._add_local_box(ents, x0, y0, z0, x1, y1, z1)
        face = ents.add_face(
          Geom::Point3d.new(x0, y0, z0),
          Geom::Point3d.new(x1, y0, z0),
          Geom::Point3d.new(x1, y1, z0),
          Geom::Point3d.new(x0, y1, z0)
        )
        return unless face
        face.reverse! if face.normal.z < 0
        face.pushpull(z1 - z0)
      end

      # Append/refresh this opening's spec on the wall's attribute dict.
      def self._record_opening_on_wall(wall_group, ai_id, wall_ai_id, params)
        existing = wall_group.get_attribute("su_mcp_bridge", "openings_spec") || []
        existing.reject! { |o| o["ai_id"] == ai_id }
        existing << params.merge("ai_id" => ai_id, "wall_id" => wall_ai_id)
        wall_group.set_attribute("su_mcp_bridge", "openings_spec", existing)
      end

      # Search all walls for the one carrying this opening in its attribute list.
      def self._find_wall_for_opening(model, ai_id)
        model.active_entities.each do |ent|
          next unless ent.is_a?(Sketchup::Group) && ent.valid?
          ops = ent.get_attribute("su_mcp_bridge", "openings_spec") || []
          return ent.get_attribute("su_mcp_bridge", "ai_id") if ops.any? { |o| o["ai_id"] == ai_id }
        end
        nil
      end
    end
  end
end
