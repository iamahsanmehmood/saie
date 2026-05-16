require_relative '../logger'
require 'fileutils'
require 'json'

module SUMCPBridge
  module Ops
    module Capture
      DEFAULT_CAPTURE_DIR = "C:/su_capture".freeze
      CAP_Z_AXIS = Geom::Vector3d.new(0, 0, 1).freeze unless const_defined?(:CAP_Z_AXIS)

      PRESETS = %w[plan iso elev_n elev_e elev_s elev_w].freeze

      RESOLUTION_PRESETS = {
        "low"   => [512, 384],
        "med"   => [1024, 768],
        "high"  => [1920, 1440],
        "ultra" => [3840, 2880]
      }.freeze

      # SketchUp rendering styles
      STYLE_PRESETS = {
        "default"      => nil,                           # Use current style
        "hidden_line"  => "Hidden Line",
        "wireframe"    => "Wireframe",
        "shaded"       => "Shaded",
        "shaded_tex"   => "Shaded with Textures",
        "monochrome"   => "Monochrome",
        "xray"         => "X-Ray"
      }.freeze

      # ---------------------------------------------------------------------
      # take — single capture
      # ---------------------------------------------------------------------
      def self.take(params)
        model = Sketchup.active_model
        
        entity = nil
        if params["entity_id"]
          entity = model.find_entity_by_persistent_id(params["entity_id"].to_i)
        elsif params["ai_id"]
          entity = _find_by_attribute(model.entities, "su_mcp_bridge", "ai_id", params["ai_id"])
        elsif params["name"]
          entity = _find_by_name(model.entities, params["name"])
        end

        return { "error" => "Model is empty or entity not found" } if entity.nil? && model.bounds.empty?

        preset = (params["preset"] || "iso").to_s
        return { "error" => "Unknown preset: #{preset}" } unless PRESETS.include?(preset)

        resolution = (params["resolution"] || "med").to_s
        width  = (params["width"]  || RESOLUTION_PRESETS[resolution][0]).to_i
        height = (params["height"] || RESOLUTION_PRESETS[resolution][1]).to_i

        save_dir = params["save_dir"] || DEFAULT_CAPTURE_DIR
        if params["project_assets_dir"] && !params["project_assets_dir"].empty?
          save_dir = params["project_assets_dir"]
        elsif params["project_captures_dir"] && !params["project_captures_dir"].empty?
          save_dir = params["project_captures_dir"]
        end
        FileUtils.mkdir_p(save_dir) unless Dir.exist?(save_dir)

        # START ISOLATION OP
        model.start_operation("Capture Isolate", false)
        
        target = entity
        if entity && params["isolate"]
          # Create a temp group at origin to hold the instance
          temp_grp = model.entities.add_group
          begin
            definition = entity.respond_to?(:definition) ? entity.definition : entity.entities.parent
            temp_grp.entities.add_instance(definition, Geom::Transformation.new)
            
            # Hide all other root entities
            model.entities.each { |e| e.hidden = true if e != temp_grp }
            target = temp_grp
          rescue => e
            SUMCPBridge::Logger.warn("Failed to isolate entity: #{e.message}")
            target = entity
          end
        end

        bb = target ? target.bounds : model.bounds
        _set_camera_for_preset(model.active_view, bb, preset)
        
        if target
          # Zoom to target and then zoom out slightly (by 15%) to leave a comfortable margin
          model.active_view.zoom(target)
          begin
            # In SketchUp, passing a float to zoom scales the view. 
            # Numbers < 1.0 zoom in, > 1.0 zoom out.
            model.active_view.zoom(1.15)
          rescue
            # Ignore if zoom float fails
          end
        else
          model.active_view.zoom_extents
        end

        # Apply style if requested
        style_key = params["style"]
        _apply_style(model, style_key) if style_key && style_key != "default"

        annotated = params["annotated"] == true
        suffix = annotated ? "_annotated" : ""
        filename = File.join(save_dir, "#{preset}#{suffix}_#{Time.now.to_i}.png")

        # Force UI to update before taking picture
        model.active_view.refresh if params["isolate"]

        model.active_view.write_image(
          filename: filename, width: width, height: height,
          antialias: true, transparent: false
        )

        scene_at_view = _build_scene_at_view(model, bb, preset, width, height)
        sidecar_path = filename.sub(/\.png$/, ".scene.json")
        File.write(sidecar_path, JSON.generate(scene_at_view)) rescue nil

        # ABORT ISOLATION OP (restores everything immediately!)
        model.abort_operation

        SUMCPBridge::Logger.debug("view.capture #{preset} -> #{filename}")

        {
          "preset"        => preset,
          "path"          => filename,
          "scene_at_view" => sidecar_path,
          "width"         => width,
          "height"        => height,
          "resolution"    => resolution,
          "status"        => "captured"
        }
      end

      # ---------------------------------------------------------------------
      # capture_canonical — render plan + iso + 4 elevations in one batch
      # ---------------------------------------------------------------------
      def self.canonical(params)
        save_dir = params["save_dir"] || DEFAULT_CAPTURE_DIR
        FileUtils.mkdir_p(save_dir) unless Dir.exist?(save_dir)

        # Resolve resolution defaults: med (1024x768) per spec.
        resolution = (params["resolution"] || "med").to_s
        width  = (params["width"]  || RESOLUTION_PRESETS[resolution][0]).to_i
        height = (params["height"] || RESOLUTION_PRESETS[resolution][1]).to_i

        captures = []
        PRESETS.each do |preset|
          res = take(params.merge("preset" => preset, "save_dir" => save_dir,
                                  "width" => width, "height" => height))
          captures << res
        end

        { "captures" => captures, "save_dir" => save_dir, "status" => "ok" }
      end

      def self.clear_model(_params)
        begin
          SUMCPBridge::Ops::Lifecycle.auto_save
        rescue NameError
          # Ignore
        end
        model = Sketchup.active_model
        model.start_operation("Clear Model", true)
        model.entities.clear!
        model.commit_operation
        SUMCPBridge::AI_ID.reset
        SUMCPBridge::Logger.info("model cleared")
        { "status" => "cleared" }
      end

      # ---------------------------------------------------------------------
      # Camera setup
      # ---------------------------------------------------------------------
      def self._set_camera_for_preset(view, bb, preset)
        center = bb.center
        diag = bb.diagonal
        diag = 100 if diag < 1

        case preset
        when "plan"
          eye = Geom::Point3d.new(center.x, center.y, center.z + diag)
          up  = Geom::Vector3d.new(0, 1, 0)
          cam = Sketchup::Camera.new(eye, center, up)
          cam.perspective = false
        when "iso"
          dist = diag * 1.2
          eye = Geom::Point3d.new(center.x + dist * 0.6, center.y - dist * 0.6, center.z + dist * 0.5)
          cam = Sketchup::Camera.new(eye, center, CAP_Z_AXIS)
          cam.perspective = true
        when "elev_n"
          eye = Geom::Point3d.new(center.x, center.y + diag, center.z)
          cam = Sketchup::Camera.new(eye, center, CAP_Z_AXIS); cam.perspective = false
        when "elev_s"
          eye = Geom::Point3d.new(center.x, center.y - diag, center.z)
          cam = Sketchup::Camera.new(eye, center, CAP_Z_AXIS); cam.perspective = false
        when "elev_e"
          eye = Geom::Point3d.new(center.x + diag, center.y, center.z)
          cam = Sketchup::Camera.new(eye, center, CAP_Z_AXIS); cam.perspective = false
        when "elev_w"
          eye = Geom::Point3d.new(center.x - diag, center.y, center.z)
          cam = Sketchup::Camera.new(eye, center, CAP_Z_AXIS); cam.perspective = false
        end
        view.camera = cam
      end

      # ---------------------------------------------------------------------
      # scene_at_view sidecar — compact text-readable description of what's
      # in the frame so the AI can read JSON instead of pixels when possible.
      # ---------------------------------------------------------------------
      def self._build_scene_at_view(model, bb, preset, width, height)
        cam = model.active_view.camera

        entities = []
        model.active_entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          ai_id = ent.get_attribute("su_mcp_bridge", "ai_id")
          next unless ai_id
          type = ent.get_attribute("su_mcp_bridge", "type") || "unknown"
          eb = ent.bounds
          entities << {
            "ai_id" => ai_id,
            "type"  => type,
            "bounds" => {
              "min" => eb.min.to_a, "max" => eb.max.to_a,
              "width" => eb.width, "depth" => eb.depth, "height" => eb.height
            }
          }
        end

        {
          "preset" => preset,
          "image" => { "width" => width, "height" => height },
          "camera" => {
            "eye"        => cam.eye.to_a,
            "target"     => cam.target.to_a,
            "up"         => cam.up.to_a,
            "perspective" => cam.perspective?
          },
          "world_bounds" => { "min" => bb.min.to_a, "max" => bb.max.to_a },
          "visible_entities" => entities,
          "model_summary" => {
            "entity_count" => entities.length,
            "level_names"  => model.layers.map(&:name)
          }
        }
      end
      # Apply SketchUp rendering style
      def self._apply_style(model, style_key)
        style_name = STYLE_PRESETS[style_key.to_s]
        return unless style_name

        styles = model.styles
        target = styles.find { |s| s.name == style_name || s.name.include?(style_name) }
        if target
          styles.selected_style = target
          Logger.debug("Applied style: #{style_name}")
        else
          Logger.warn("Style not found: #{style_name}, available: #{styles.map(&:name).join(', ')}")
        end
      rescue => e
        Logger.warn("Style application failed: #{e.message}")
      end

      def self._find_by_attribute(entities, dict, key, value)
        entities.each do |e|
          return e if e.respond_to?(:get_attribute) && e.get_attribute(dict, key) == value
          if e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
            ents = e.is_a?(Sketchup::Group) ? e.entities : e.definition.entities
            found = _find_by_attribute(ents, dict, key, value)
            return found if found
          end
        end
        nil
      end

      def self._find_by_name(entities, name)
        entities.each do |e|
          return e if e.respond_to?(:name) && e.name == name
          if e.is_a?(Sketchup::Group) || e.is_a?(Sketchup::ComponentInstance)
            ents = e.is_a?(Sketchup::Group) ? e.entities : e.definition.entities
            found = _find_by_name(ents, name)
            return found if found
          end
        end
        nil
      end
    end
  end
end
