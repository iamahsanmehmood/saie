module SUMCPBridge
  module Ops
    module Dimension
      def self.create(params)
        ai_id = params["ai_id"] || "DIM_#{Time.now.to_i}"
        
        # Dimensions are expected in INCHES
        start_pt_array = params["start_pt"]
        end_pt_array = params["end_pt"]
        offset_vector_array = params["offset_vector"] || [0, 0, 10]
        
        start_pt = Geom::Point3d.new(*start_pt_array)
        end_pt = Geom::Point3d.new(*end_pt_array)
        offset_vector = Geom::Vector3d.new(*offset_vector_array)
        
        model = Sketchup.active_model
        entities = model.active_entities
        
        dim = entities.add_dimension_linear(start_pt, end_pt, offset_vector)
        
        SUMCPBridge::AI_ID.set(dim, ai_id)
        
        { "ai_id" => ai_id, "entity_id" => dim.entityID, "status" => "created" }
      end
    end
  end
end
