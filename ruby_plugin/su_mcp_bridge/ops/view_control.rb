require_relative '../logger'
require 'set'

module SUMCPBridge
  module Ops
    # ViewControl — camera + selection + isolation operations.
    # These manipulate what the user sees and what's targeted by other ops.
    # Camera + selection changes are NOT wrapped in start_operation (they
    # aren't undoable in SketchUp). Hide/isolate IS wrapped because hiding
    # entities is part of the undo stack.
    module ViewControl
      DICT = 'su_mcp_bridge'.freeze

      class << self
        # ─── Camera ───────────────────────────────────────────────────────

        # Orbit the camera around its current target point.
        # horizontal: degrees, rotation around Z (around-the-world)
        # vertical:   degrees, rotation around the camera's right axis
        def orbit(params)
          h = params['horizontal'].to_f
          v = params['vertical'].to_f
          view = Sketchup.active_model.active_view
          cam  = view.camera

          eye, target, up = cam.eye, cam.target, cam.up
          vec = target.vector_to(eye)

          if h.abs > 1e-6
            t = Geom::Transformation.rotation(target, Z_AXIS, h.degrees)
            vec = vec.transform(t)
            up  = up.transform(t)
          end
          if v.abs > 1e-6
            right = vec.cross(up)
            unless right.length == 0
              right.normalize!
              t = Geom::Transformation.rotation(target, right, v.degrees)
              vec = vec.transform(t)
              up  = up.transform(t)
            end
          end

          new_eye = target.offset(vec)
          new_cam = Sketchup::Camera.new(new_eye, target, up)
          new_cam.perspective = cam.perspective?
          new_cam.fov = cam.fov if cam.perspective?
          view.camera = new_cam

          { 'status' => 'ok', 'eye' => new_eye.to_a, 'target' => target.to_a }
        end

        # Zoom by factor. <1 zooms in, >1 zooms out.
        # SketchUp's view.zoom(numeric) does exactly this.
        def zoom(params)
          f = params['factor'].to_f
          f = 1.0 if f <= 0
          Sketchup.active_model.active_view.zoom(f)
          { 'status' => 'ok', 'factor' => f }
        end

        def zoom_extents(_params)
          Sketchup.active_model.active_view.zoom_extents
          { 'status' => 'ok' }
        end

        def zoom_selection(_params)
          model = Sketchup.active_model
          sel = model.selection
          return { 'error' => 'nothing selected' } if sel.empty?
          model.active_view.zoom(sel.to_a)
          { 'status' => 'ok', 'count' => sel.size }
        end

        # Pan: shift eye + target by the same vector in world coordinates.
        def pan(params)
          dx = params['dx'].to_f
          dy = params['dy'].to_f
          dz = params['dz'].to_f
          view = Sketchup.active_model.active_view
          cam = view.camera
          vec = Geom::Vector3d.new(dx, dy, dz)
          new_cam = Sketchup::Camera.new(cam.eye.offset(vec), cam.target.offset(vec), cam.up)
          new_cam.perspective = cam.perspective?
          new_cam.fov = cam.fov if cam.perspective?
          view.camera = new_cam
          { 'status' => 'ok', 'delta' => [dx, dy, dz] }
        end

        # Set camera directly — eye/target/up arrays + perspective/fov flags.
        def set_camera(params)
          view = Sketchup.active_model.active_view
          cam = view.camera
          eye    = params['eye']    ? Geom::Point3d.new(*params['eye'])    : cam.eye
          target = params['target'] ? Geom::Point3d.new(*params['target']) : cam.target
          up     = params['up']     ? Geom::Vector3d.new(*params['up'])    : cam.up
          new_cam = Sketchup::Camera.new(eye, target, up)
          new_cam.perspective = params['perspective'] if params.key?('perspective')
          new_cam.fov = params['fov'].to_f if params['fov']
          view.camera = new_cam
          { 'status' => 'ok', 'eye' => eye.to_a, 'target' => target.to_a, 'up' => up.to_a }
        end

        # Read current camera state.
        def get_camera(_params)
          cam = Sketchup.active_model.active_view.camera
          {
            'eye'         => cam.eye.to_a,
            'target'      => cam.target.to_a,
            'up'          => cam.up.to_a,
            'perspective' => cam.perspective?,
            'fov'         => (cam.perspective? ? cam.fov : nil)
          }
        end

        # ─── Selection ────────────────────────────────────────────────────

        # mode: 'add' (default), 'replace', 'toggle'
        def select(params)
          model = Sketchup.active_model
          entities = resolve_entities(model, params)
          return { 'error' => 'no entities resolved' } if entities.empty?
          mode = (params['mode'] || 'add').to_s
          model.selection.clear if mode == 'replace'
          entities.each do |e|
            if mode == 'toggle' && model.selection.include?(e)
              model.selection.remove(e)
            else
              model.selection.add(e)
            end
          end
          { 'status' => 'ok', 'mode' => mode, 'count' => model.selection.size }
        end

        def deselect(params)
          model = Sketchup.active_model
          entities = resolve_entities(model, params)
          entities.each { |e| model.selection.remove(e) if model.selection.include?(e) }
          { 'status' => 'ok', 'count' => model.selection.size }
        end

        def clear_selection(_params)
          Sketchup.active_model.selection.clear
          { 'status' => 'ok', 'count' => 0 }
        end

        def selection_info(_params)
          model = Sketchup.active_model
          items = model.selection.map do |e|
            {
              'persistent_id' => (e.persistent_id.to_s rescue nil),
              'ai_id'         => (e.get_attribute(DICT, 'ai_id') rescue nil),
              'type'          => (e.get_attribute(DICT, 'type') rescue nil) ||
                                 e.class.to_s.sub('Sketchup::', '').downcase,
              'name'          => (e.respond_to?(:name) ? e.name : nil)
            }
          end
          { 'count' => items.size, 'items' => items }
        end

        # ─── Isolation (hide everything else) ─────────────────────────────

        def isolate(params)
          model = Sketchup.active_model
          targets = resolve_entities(model, params)
          targets = model.selection.to_a if targets.empty? && !model.selection.empty?
          return { 'error' => 'no targets (pass ai_id / persistent_id or select first)' } if targets.empty?

          target_set = Set.new(targets)
          model.start_operation('Isolate', true)
          hidden = 0
          model.entities.each do |e|
            next if target_set.include?(e)
            next if e.hidden?
            e.hidden = true
            hidden += 1
          end
          model.commit_operation
          { 'status' => 'ok', 'isolated' => targets.size, 'hidden_count' => hidden }
        end

        def unisolate(_params)
          model = Sketchup.active_model
          model.start_operation('Show All', true)
          shown = 0
          model.entities.each do |e|
            if e.hidden?
              e.hidden = false
              shown += 1
            end
          end
          model.commit_operation
          { 'status' => 'ok', 'shown_count' => shown }
        end

        # ─── Helpers ──────────────────────────────────────────────────────

        # Resolve entities from any of:
        #   ai_id, ai_ids[], persistent_id, persistent_ids[], name
        def resolve_entities(model, params)
          ids = []
          ids.concat(Array(params['ai_ids']))
          ids.concat(Array(params['persistent_ids']))
          ids << params['ai_id']         if params['ai_id']
          ids << params['persistent_id'] if params['persistent_id']
          ids.compact!

          out = []
          ids.each do |raw|
            id = raw.to_s
            ent = if id =~ /\A\d+\z/
                    model.find_entity_by_persistent_id(id.to_i) rescue nil
                  else
                    find_by_attribute(model.entities, DICT, 'ai_id', id)
                  end
            ent ||= find_by_attribute(model.entities, DICT, 'ai_id', id) if id =~ /\A\d+\z/
            out << ent if ent && ent.valid?
          end

          if params['name']
            n = find_by_name(model.entities, params['name'].to_s)
            out << n if n && n.valid?
          end

          out.uniq
        end

        def find_by_attribute(entities, dict, key, value)
          entities.each do |e|
            return e if e.respond_to?(:get_attribute) && e.get_attribute(dict, key) == value
            if e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
              ents = e.is_a?(Sketchup::Group) ? e.entities : e.definition.entities
              found = find_by_attribute(ents, dict, key, value)
              return found if found
            end
          end
          nil
        end

        def find_by_name(entities, name)
          entities.each do |e|
            return e if e.respond_to?(:name) && e.name == name
            if e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
              ents = e.is_a?(Sketchup::Group) ? e.entities : e.definition.entities
              found = find_by_name(ents, name)
              return found if found
            end
          end
          nil
        end
      end
    end
  end
end
