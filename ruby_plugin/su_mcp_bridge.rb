require 'sketchup.rb'
require 'extensions.rb'

module SUMCPBridge
  unless file_loaded?(__FILE__)
    ex = SketchupExtension.new('SAIE — SketchUp Automation & Intelligence Engine', 'su_mcp_bridge/main')
    ex.description = 'SAIE — Unified pipeline for AI-powered architectural modeling, BIM analysis, and rendering via JSON-RPC WebSocket.'
    ex.version     = '1.0.0'
    ex.creator     = 'Ahsan Mehmood'
    Sketchup.register_extension(ex, true)
    file_loaded(__FILE__)
  end
end
