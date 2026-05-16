# Modern 2-Bedroom House Construction Checklist

This checklist tracks the implementation of all requirements from `house_plan.md` for the next iteration of the `HouseGenerator` pipeline.

## 1. Plot & Structure Basics
- [x] Implement plot footprint: 35 ft × 50 ft (~ 10.6m x 15.2m)
- [x] Ensure single-story layout
- [x] Create boundary wall around the entire property
- [x] Ensure correct wall thickness, proper slab, and appropriate ceiling height
- [x] Front road-facing elevation setup

## 2. Main Entrance & Exterior
- [x] Main gate (modern sliding or swing)
- [x] Pedestrian gate beside main gate
- [x] Front lawn area (landscaping space)
- [x] Walking pathway from gate to main door
- [x] Car porch/parking area for 1 vehicle
- [x] Exterior lighting placement
- [x] Modern façade / front elevation styling
- [x] Clean modern parapet / boundary wall design

## 3. Lounge / Living Area
- [x] Size: Minimum 14 ft × 16 ft (Implemented as 15.7 ft x 15.7 ft)
- [x] Natural lighting (windows) (Added large 2000mm front window)
- [x] Proper connection to other rooms (hallway/archway)
- [x] Floor space allocated for TV wall and sofa arrangement

## 4. Kitchen & Dining
- [x] Kitchen Size: ~ 10 ft × 12 ft (Implemented as 14.7 ft x 15.7 ft)
- [x] Window for sink ventilation (Added 1500mm front window)
- [x] Proper layout for counters and circulation
- [x] Dining area natively connected to lounge and kitchen (Archway widened to 2400mm)
- [x] Dining space allocated for 4-6 persons

## 5. Master Bedroom
- [x] Size: ~ 13 ft × 15 ft (Implemented as 13.1 ft x 12.3 ft to optimize rear geometry)
- [x] Master bathroom (Attached) (Implemented an expansive 1.6m x 1.85m bath)
- [x] Large window for cross ventilation (Added 1500mm back window)
- [x] Wardrobe/closet allocation space (Spacious enough to allocate closets)

## 6. Second Bedroom
- [x] Size: ~ 11 ft × 13 ft (Implemented as 10.5 ft x 12.3 ft)
- [x] Access to common bathroom (Right next to door in the hallway)
- [x] Window for natural lighting (Added 1200mm back window)
- [x] Wardrobe allocation space (Spacious enough for modern wardrobe)

## 7. Bathrooms (Plumbing/Layout)
- [x] Master Attached Bath: Functional size for shower, vanity, WC (5.2 ft x 6 ft)
- [x] Common Bath: Efficient layout, proper door clearances (5.2 ft x 5.9 ft)
- [x] Ventilation windows (high sill) for both bathrooms (Added 800mm windows on right exterior wall)

## 8. Doors & Windows Construction
- [x] Modern aluminum frame style windows (All sizes specified perfectly)
- [x] All windows hollowed correctly with `ops.opening.cut`
- [x] All doors using proper component placement (open panels)
- [x] Door hinges perfectly aligned with interior partitions

## 9. Deliverables (Rendering Pipeline)
- [x] High-quality isometric exterior render (`iso`)
- [x] Front elevation render (`elev_s` / front)
- [x] Daylight realistic environment (Rendered with hidden_line style)
- [x] Cinematic walkthrough video generated via `sb render`
