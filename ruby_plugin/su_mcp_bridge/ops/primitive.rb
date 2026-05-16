module SUMCPBridge
  module Ops
    module PrimitiveOps
      def self.create(params)
        model = Sketchup.active_model
        ents  = model.active_entities
        
        ai_id = params["ai_id"] || params["id"]
        upserted = false
        unless ai_id && !ai_id.empty?
          pos_mm = params.dig("transform", "position_mm")
          ai_id = SUMCPBridge::AI_ID.auto_name(params["kind"] || :primitive, pos_mm)
        else
          existing = SUMCPBridge::AI_ID.find(ai_id)
          if existing && existing.valid?
            existing.erase!
            SUMCPBridge::AI_ID.evict(ai_id)
            upserted = true
          end
        end
        tags = params["tags"] || []
        kind = params["kind"]
        dims = params["dimensions"] || {}
        transform = params["transform"] || {}
        
        # Position (mm to inches)
        pos = transform["position_mm"] || [0, 0, 0]
        px, py, pz = pos[0] / 25.4, pos[1] / 25.4, pos[2] / 25.4
        
        group = ents.add_group
        ge = group.entities
        
        case kind
        when "box"
          w = (dims["width_mm"] || 1000).to_f / 25.4
          d = (dims["depth_mm"] || 1000).to_f / 25.4
          h = (dims["height_mm"] || 1000).to_f / 25.4
          face = ge.add_face(
            Geom::Point3d.new(0, 0, 0),
            Geom::Point3d.new(w, 0, 0),
            Geom::Point3d.new(w, d, 0),
            Geom::Point3d.new(0, d, 0)
          )
          face.reverse! if face.normal.z < 0
          face.pushpull(h)
          
        when "cylinder"
          r = (dims["radius_mm"] || 500).to_f / 25.4
          h = (dims["height_mm"] || 1000).to_f / 25.4
          n = (dims["segments"] || 24).to_i
          center = Geom::Point3d.new(0, 0, 0)
          normal = Geom::Vector3d.new(0, 0, 1)
          circle = ge.add_circle(center, normal, r, n)
          face = ge.add_face(circle)
          face.reverse! if face.normal.z < 0
          face.pushpull(h)
          
        when "sphere"
          r = (dims["radius_mm"] || 500).to_f / 25.4
          n = (dims["segments"] || 24).to_i
          # Build sphere via half-circle revolution
          center = Geom::Point3d.new(0, 0, 0)
          # Create a half-circle profile path
          pts = []
          (0..n).each do |i|
            angle = Math::PI * i / n
            pts << Geom::Point3d.new(r * Math.cos(angle), 0, r * Math.sin(angle))
          end
          # Add path edges
          path_edges = []
          (0...pts.length-1).each do |i|
            path_edges << ge.add_line(pts[i], pts[i+1])
          end
          # Create circle for follow-me
          circle = ge.add_circle(Geom::Point3d.new(r, 0, 0), Geom::Vector3d.new(0, 0, 1), r, n)
          face = ge.add_face(circle)
          # Use follow_me with the half-circle path
          face.followme(path_edges)
          
        when "cone"
          r = (dims["radius_mm"] || 500).to_f / 25.4
          h = (dims["height_mm"] || 1000).to_f / 25.4
          n = (dims["segments"] || 24).to_i
          # Create base circle
          center = Geom::Point3d.new(0, 0, 0)
          normal = Geom::Vector3d.new(0, 0, 1)
          circle_edges = ge.add_circle(center, normal, r, n)
          # Connect each edge vertex to the apex
          apex = Geom::Point3d.new(0, 0, h)
          circle_edges.each do |edge|
            ge.add_line(edge.start.position, apex)
          end
          # Add base face
          ge.add_face(circle_edges)
          
        when "pyramid"
          w = (dims["width_mm"] || 1000).to_f / 25.4
          d = (dims["depth_mm"] || 1000).to_f / 25.4
          h = (dims["height_mm"] || 1000).to_f / 25.4
          hw, hd = w/2.0, d/2.0
          apex = Geom::Point3d.new(0, 0, h)
          p1 = Geom::Point3d.new(-hw, -hd, 0)
          p2 = Geom::Point3d.new( hw, -hd, 0)
          p3 = Geom::Point3d.new( hw,  hd, 0)
          p4 = Geom::Point3d.new(-hw,  hd, 0)
          ge.add_face(p1, p2, p3, p4)  # base
          ge.add_face(p1, p2, apex)
          ge.add_face(p2, p3, apex)
          ge.add_face(p3, p4, apex)
          ge.add_face(p4, p1, apex)
        when "text"
          text = params["text"] || "Text"
          h = (dims["height_mm"] || 1000).to_f / 25.4
          ge.add_3d_text(text, TextAlignLeft, "Arial", true, false, h, 0.0, 0.5, true, 5.0)
          
        else
          return { "error" => "Unknown primitive kind: #{kind}" }
        end
        
        # Compose final transformation matrix
        tr = Geom::Transformation.new
        
        # 1. Translation
        if px != 0 || py != 0 || pz != 0
          tr_pos = Geom::Transformation.translation(Geom::Vector3d.new(px, py, pz))
          tr = tr_pos * tr
        end
        
        # 2. Rotation around Z, Y, X (applied locally at origin before translation)
        rot = transform["rotation_deg"] || [0, 0, 0]
        if rot[2] != 0
          tr_rotZ = Geom::Transformation.rotation(Geom::Point3d.new(0,0,0), Geom::Vector3d.new(0,0,1), rot[2].degrees)
          tr = tr * tr_rotZ
        end
        if rot[1] != 0
          tr_rotY = Geom::Transformation.rotation(Geom::Point3d.new(0,0,0), Geom::Vector3d.new(0,1,0), rot[1].degrees)
          tr = tr * tr_rotY
        end
        if rot[0] != 0
          tr_rotX = Geom::Transformation.rotation(Geom::Point3d.new(0,0,0), Geom::Vector3d.new(1,0,0), rot[0].degrees)
          tr = tr * tr_rotX
        end
        
        group.transform!(tr)
        
        SUMCPBridge::AI_ID.set(group, ai_id, tags: tags)
        { "ai_id" => ai_id, "guid" => group.guid, "kind" => kind, "status" => upserted ? "upserted" : "created" }
      end
    end
  end
end
