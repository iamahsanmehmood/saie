require_relative '../logger'
require 'fileutils'
require 'json'

module SUMCPBridge
  module Ops
    module Animation
      DEFAULT_WALKTHROUGH_DIR = "C:/su_capture/walkthrough".freeze

      # =====================================================================
      # walkthrough — automated multi-frame camera sweep rendered to PNGs.
      #
      # Presets:
      #   "orbit"      — 360° aerial orbit around model center
      #   "flythrough"  — linear path from start_pt to end_pt through interior
      #   "cinematic"   — smooth arc from low angle to high angle
      #
      # Params:
      #   preset         (string, default "orbit")
      #   frames         (int,    default 120)
      #   fps            (int,    default 30)
      #   orbit_height_mm (float, default 5000)
      #   save_dir       (string, default C:/su_capture/walkthrough)
      #   resolution     (string, default "med")
      #   start_pt       (array,  for flythrough [x,y,z] mm)
      #   end_pt         (array,  for flythrough [x,y,z] mm)
      # =====================================================================
      def self.walkthrough(params)
        model = Sketchup.active_model
        bb = model.bounds
        return { "error" => "Model is empty" } if bb.empty?

        preset   = (params["preset"] || "orbit").to_s
        frames   = (params["frames"] || 120).to_i
        fps      = (params["fps"] || 30).to_i
        save_dir = params["save_dir"] || DEFAULT_WALKTHROUGH_DIR
        res_key  = (params["resolution"] || "med").to_s

        res_map = { "low" => [640, 480], "med" => [1280, 720], "high" => [1920, 1080] }
        width, height = res_map[res_key] || res_map["med"]

        FileUtils.mkdir_p(save_dir)

        center = bb.center
        diag = bb.diagonal
        diag = 100 if diag < 1

        Logger.info("walkthrough: #{preset} #{frames} frames @ #{width}x#{height}")

        case preset
        when "orbit"
          _render_orbit(model, center, diag, frames, width, height, save_dir, params)
        when "flythrough"
          _render_flythrough(model, center, diag, frames, width, height, save_dir, params)
        when "cinematic"
          _render_cinematic(model, center, diag, frames, width, height, save_dir, params)
        else
          return { "error" => "Unknown preset: #{preset}" }
        end

        # Attempt FFmpeg stitch
        mp4_path = _stitch_mp4(save_dir, fps)

        {
          "preset"     => preset,
          "frames"     => frames,
          "fps"        => fps,
          "save_dir"   => save_dir,
          "mp4"        => mp4_path,
          "resolution" => "#{width}x#{height}",
          "status"     => "complete"
        }
      rescue => e
        Logger.error("walkthrough failed: #{e.message}")
        { "error" => "walkthrough failed: #{e.message}" }
      end

      private

      UP = Geom::Vector3d.new(0, 0, 1)
      MM = 1.0 / 25.4  # mm to inches

      def self._render_orbit(model, center, diag, frames, w, h, save_dir, params)
        orbit_h = ((params["orbit_height_mm"] || 5000).to_f) * MM
        radius = diag * 1.2

        frames.times do |i|
          angle = (2.0 * Math::PI * i) / frames
          ex = center.x + radius * Math.cos(angle)
          ey = center.y + radius * Math.sin(angle)
          ez = center.z + orbit_h

          eye = Geom::Point3d.new(ex, ey, ez)
          cam = Sketchup::Camera.new(eye, center, UP)
          cam.perspective = true
          model.active_view.camera = cam

          path = File.join(save_dir, "frame_%04d.png" % i)
          model.active_view.write_image(filename: path, width: w, height: h, antialias: true)
        end
      end

      def self._render_flythrough(model, center, diag, frames, w, h, save_dir, params)
        s = params["start_pt"] || [center.x - diag * 0.8, center.y, center.z + diag * 0.3 / MM]
        e = params["end_pt"]   || [center.x + diag * 0.8, center.y, center.z + diag * 0.3 / MM]

        sx, sy, sz = s[0].to_f * MM, s[1].to_f * MM, s[2].to_f * MM
        ex, ey, ez = e[0].to_f * MM, e[1].to_f * MM, e[2].to_f * MM

        frames.times do |i|
          t = i.to_f / (frames - 1).to_f
          px = sx + (ex - sx) * t
          py = sy + (ey - sy) * t
          pz = sz + (ez - sz) * t

          eye = Geom::Point3d.new(px, py, pz)
          # Look ahead along the path
          look_t = [(t + 0.1), 1.0].min
          lx = sx + (ex - sx) * look_t
          ly = sy + (ey - sy) * look_t
          lz = sz + (ez - sz) * look_t - diag * 0.1
          target = Geom::Point3d.new(lx, ly, lz)

          cam = Sketchup::Camera.new(eye, target, UP)
          cam.perspective = true
          cam.fov = 60
          model.active_view.camera = cam

          path = File.join(save_dir, "frame_%04d.png" % i)
          model.active_view.write_image(filename: path, width: w, height: h, antialias: true)
        end
      end

      def self._render_cinematic(model, center, diag, frames, w, h, save_dir, _params)
        radius = diag * 1.5
        start_elev = 10.0 * Math::PI / 180.0   # 10 degrees
        end_elev   = 60.0 * Math::PI / 180.0   # 60 degrees
        start_azim = -30.0 * Math::PI / 180.0
        end_azim   = 45.0 * Math::PI / 180.0

        frames.times do |i|
          t = i.to_f / (frames - 1).to_f
          # Smooth ease-in-out
          t_smooth = t * t * (3.0 - 2.0 * t)

          elev = start_elev + (end_elev - start_elev) * t_smooth
          azim = start_azim + (end_azim - start_azim) * t_smooth

          ex = center.x + radius * Math.cos(elev) * Math.cos(azim)
          ey = center.y + radius * Math.cos(elev) * Math.sin(azim)
          ez = center.z + radius * Math.sin(elev)

          eye = Geom::Point3d.new(ex, ey, ez)
          cam = Sketchup::Camera.new(eye, center, UP)
          cam.perspective = true
          cam.fov = 45
          model.active_view.camera = cam

          path = File.join(save_dir, "frame_%04d.png" % i)
          model.active_view.write_image(filename: path, width: w, height: h, antialias: true)
        end
      end

      def self._stitch_mp4(save_dir, fps)
        ffmpeg = _find_ffmpeg
        return nil unless ffmpeg

        mp4_path = File.join(save_dir, "walkthrough.mp4")
        pattern = File.join(save_dir, "frame_%04d.png")

        cmd = "\"#{ffmpeg}\" -y -framerate #{fps} -i \"#{pattern}\" -c:v libx264 -pix_fmt yuv420p -crf 18 \"#{mp4_path}\""
        Logger.info("Stitching video: #{cmd}")
        system(cmd)

        File.exist?(mp4_path) ? mp4_path : nil
      rescue => e
        Logger.warn("FFmpeg stitch failed: #{e.message}")
        nil
      end

      def self._find_ffmpeg
        # Check common locations
        paths = [
          "ffmpeg",
          "C:/ffmpeg/bin/ffmpeg.exe",
          "C:/Program Files/ffmpeg/bin/ffmpeg.exe",
          File.join(ENV["USERPROFILE"] || "", "ffmpeg", "bin", "ffmpeg.exe")
        ]
        paths.each do |p|
          return p if system("\"#{p}\" -version > nul 2>&1")
        end
        Logger.warn("FFmpeg not found — frames saved but no MP4 generated")
        nil
      end
    end
  end
end
