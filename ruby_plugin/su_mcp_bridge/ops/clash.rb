require_relative '../logger'
require 'json'

module SUMCPBridge
  module Ops
    module Clash
      MM_TO_IN = 1.0 / 25.4

      # Detect AABB overlaps between all AI-tracked entities.
      # Params:
      #   tolerance_mm (float, default 1.0) : ignore overlaps smaller than this
      #   ignore_pairs (array, optional)    : [[id_a, id_b], ...] pairs to skip
      def self.detect(params)
        tolerance = ((params["tolerance_mm"] || 1.0).to_f) * MM_TO_IN
        ignore_set = {}
        (params["ignore_pairs"] || []).each do |pair|
          key = [pair[0], pair[1]].sort.join("|")
          ignore_set[key] = true
        end

        model = Sketchup.active_model
        tracked = []

        model.active_entities.each do |ent|
          next unless ent.respond_to?(:get_attribute) && ent.valid?
          ai_id = ent.get_attribute("su_mcp_bridge", "ai_id")
          next unless ai_id
          type = ent.get_attribute("su_mcp_bridge", "type") || "unknown"
          bb = ent.bounds
          tracked << { "ai_id" => ai_id, "type" => type, "ent" => ent, "bb" => bb }
        end

        clashes = []

        tracked.each_with_index do |a, i|
          tracked[(i + 1)..-1].each do |b|
            # Skip known parent-child (wall <-> opening)
            pair_key = [a["ai_id"], b["ai_id"]].sort.join("|")
            next if ignore_set[pair_key]

            # Skip wall-opening pairs (openings are children of walls)
            next if _parent_child?(a, b)

            # AABB overlap test
            bb_a = a["bb"]
            bb_b = b["bb"]
            next unless _aabb_overlap?(bb_a, bb_b, tolerance)

            overlap = _overlap_volume(bb_a, bb_b)
            severity = _classify_severity(overlap, a, b)

            clashes << {
              "entity_a" => a["ai_id"],
              "type_a"   => a["type"],
              "entity_b" => b["ai_id"],
              "type_b"   => b["type"],
              "overlap_volume_in3" => overlap,
              "severity" => severity
            }
          end
        end

        {
          "clashes" => clashes,
          "total"   => clashes.length,
          "status"  => clashes.empty? ? "clean" : "clashes_found",
          "entities_checked" => tracked.length
        }
      rescue => e
        Logger.error("clash.detect failed: #{e.message}")
        { "error" => "clash detection failed: #{e.message}" }
      end

      private

      def self._parent_child?(a, b)
        # Opening is always stored as metadata on a wall, not as a standalone entity.
        # But components attached to openings can clash with walls — that's expected.
        return true if a["type"] == "wall" && b["type"] == "opening"
        return true if b["type"] == "wall" && a["type"] == "opening"
        false
      end

      def self._aabb_overlap?(bb_a, bb_b, tolerance)
        return false if bb_a.min.x >= bb_b.max.x - tolerance
        return false if bb_a.max.x <= bb_b.min.x + tolerance
        return false if bb_a.min.y >= bb_b.max.y - tolerance
        return false if bb_a.max.y <= bb_b.min.y + tolerance
        return false if bb_a.min.z >= bb_b.max.z - tolerance
        return false if bb_a.max.z <= bb_b.min.z + tolerance
        true
      end

      def self._overlap_volume(bb_a, bb_b)
        dx = [0, [bb_a.max.x, bb_b.max.x].min - [bb_a.min.x, bb_b.min.x].max].max
        dy = [0, [bb_a.max.y, bb_b.max.y].min - [bb_a.min.y, bb_b.min.y].max].max
        dz = [0, [bb_a.max.z, bb_b.max.z].min - [bb_a.min.z, bb_b.min.z].max].max
        dx * dy * dz
      end

      def self._classify_severity(overlap, a, b)
        return "info" if overlap < 0.01
        return "warning" if overlap < 1.0
        "error"
      end
    end
  end
end
