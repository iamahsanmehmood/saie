require_relative '../logger'

module SUMCPBridge
  module Ops
    module Lifecycle
      # Save the active model. If path is provided, save to that location.
      def self.save(params)
        model = Sketchup.active_model
        path = params["path"]
        begin
          if path && !path.empty?
            result = model.save(path)
          else
            result = model.save
          end
          Logger.info("Model saved: #{model.path}")
          { "status" => result ? "saved" : "save_failed", "path" => model.path }
        rescue => e
          Logger.error("lifecycle.save failed: #{e.message}")
          { "error" => "save failed: #{e.message}" }
        end
      end

      # Save model to a new path (Save As).
      def self.save_as(params)
        path = params["path"]
        return { "error" => "path is required for save_as" } unless path && !path.empty?
        
        model = Sketchup.active_model
        begin
          result = model.save(path)
          Logger.info("Model saved as: #{path}")
          { "status" => result ? "saved" : "save_failed", "path" => path }
        rescue => e
          Logger.error("lifecycle.save_as failed: #{e.message}")
          { "error" => "save_as failed: #{e.message}" }
        end
      end

      # Create a new empty model.
      def self.new_file(_params)
        auto_save
        Sketchup.send_action("newDocument:")
        Logger.info("New file created")
        { "status" => "new_file_created" }
      end

      # Open an existing .skp file.
      def self.open_file(params)
        path = params["path"]
        return { "error" => "path is required" } unless path && !path.empty?
        return { "error" => "File not found: #{path}" } unless File.exist?(path)
        
        # If it's already the active model, just return success
        model = Sketchup.active_model
        if model.path && File.expand_path(model.path).casecmp(File.expand_path(path)) == 0
          return { "status" => "already_open", "path" => model.path }
        end
        
        auto_save
        Sketchup.open_file(path)
        Logger.info("Opened file: #{path}")
        { "status" => "opened", "path" => path }
      end

      # Close SketchUp gracefully.
      def self.close(_params)
        auto_save
        Logger.info("Closing SketchUp...")
        # Delay slightly so the response can be sent before closing
        UI.start_timer(0.5, false) { Sketchup.send_action("fixedClose:") }
        { "status" => "closing" }
      end

      # Return information about the current model.
      def self.model_info(_params)
        model = Sketchup.active_model
        {
          "title"       => model.title,
          "path"        => model.path,
          "modified"    => model.modified?,
          "description" => model.description,
          "geo_location" => model.georeferenced? ? {
            "lat" => model.shadow_info["Latitude"],
            "lng" => model.shadow_info["Longitude"]
          } : nil,
          "units" => model.options["UnitsOptions"]["LengthUnit"],
          "entity_count" => model.entities.length,
          "component_definitions" => model.definitions.length,
          "materials_count" => model.materials.length,
          "layers_count" => model.layers.length
        }
      end

      def self.auto_save
        model = Sketchup.active_model
        if model.modified? && model.path && !model.path.empty?
          model.save
          Logger.info("Auto-saved model before destructive action")
        end
      end
    end
  end
end
