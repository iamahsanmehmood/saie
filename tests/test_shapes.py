"""Build all geometric primitives in SketchUp — inline Ruby approach."""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from su_helpers import SketchUpBridge

su = SketchUpBridge(timeout=60)
if not su.is_connected():
    print("ERROR: Not connected"); sys.exit(1)

def ruby(code):
    for attempt in range(3):
        try:
            return su.exec_ruby(code)
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
            else:
                raise

def make_shape(code, name):
    try:
        ruby(code)
        print(f"  OK  {name}")
    except Exception as e:
        print(f"  ERR {name}: {e}")
    time.sleep(0.15)

# Clear
print("Clearing...")
ruby("m=Sketchup.active_model;m.start_operation('C',true);m.entities.clear!;m.commit_operation;'ok'")

print("\nCreating shapes...\n")

# === ROW 1 (back, y=280) ===

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cube_Brown";e=g.entities
f=e.add_face([0,280,0],[40,280,0],[40,320,0],[0,320,0]);f.pushpull(-40) if f
mt=m.materials.add("m1");mt.color=Sketchup::Color.new(139,90,43);g.material=mt;m.commit_operation
''', "Cube_Brown")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cube_Navy";e=g.entities
f=e.add_face([65,280,0],[110,280,0],[110,325,0],[65,325,0]);f.pushpull(-45) if f
mt=m.materials.add("m2");mt.color=Sketchup::Color.new(25,50,100);g.material=mt;m.commit_operation
''', "Cube_Navy")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Prism_Green";e=g.entities
e.add_face([135,280,0],[185,280,0],[160,280,50]);e.add_face([135,330,0],[185,330,0],[160,330,50])
e.add_face([135,280,0],[185,280,0],[185,330,0],[135,330,0]);e.add_face([185,280,0],[160,280,50],[160,330,50],[185,330,0])
e.add_face([160,280,50],[135,280,0],[135,330,0],[160,330,50])
mt=m.materials.add("m3");mt.color=Sketchup::Color.new(34,120,60);g.material=mt;m.commit_operation
''', "Prism_Green")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cylinder_Gold";e=g.entities
c=e.add_circle([235,305,0],[0,0,1],25,24);f=e.add_face(c);f.pushpull(-50) if f
mt=m.materials.add("m4");mt.color=Sketchup::Color.new(180,160,50);g.material=mt;m.commit_operation
''', "Cylinder_Gold")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cube_Orange";e=g.entities
f=e.add_face([285,280,0],[340,280,0],[340,335,0],[285,335,0]);f.pushpull(-55) if f
mt=m.materials.add("m5");mt.color=Sketchup::Color.new(220,160,30);g.material=mt;m.commit_operation
''', "Cube_Orange")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cone_Pink";e=g.entities
cx=385;cy=310;apex=Geom::Point3d.new(cx,cy,50)
c=e.add_circle([cx,cy,0],[0,0,1],20,24);e.add_face(c)
c.each{|ed| e.add_face(ed.start.position,ed.end.position,apex)}
mt=m.materials.add("m6");mt.color=Sketchup::Color.new(220,190,180);g.material=mt;m.commit_operation
''', "Cone_Pink")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Pyramid_White";e=g.entities
x=430;y=280;w=50;d=50;h=50;apex=Geom::Point3d.new(x+25,y+25,h)
e.add_face([x,y,0],[x+w,y,0],[x+w,y+d,0],[x,y+d,0])
e.add_face([x,y,0],[x+w,y,0],apex);e.add_face([x+w,y,0],[x+w,y+d,0],apex)
e.add_face([x+w,y+d,0],[x,y+d,0],apex);e.add_face([x,y+d,0],[x,y,0],apex)
mt=m.materials.add("m7");mt.color=Sketchup::Color.new(230,230,230);g.material=mt;m.commit_operation
''', "Pyramid_White")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Sphere_Red";e=g.entities
cx=535.0;cy=305.0;cz=25.0;rad=25.0;n=14
pts=Array.new(n+1){|i| lat=Math::PI*i.to_f/n-Math::PI/2.0
  Array.new(n+1){|j| lon=2*Math::PI*j.to_f/n
    Geom::Point3d.new(cx+rad*Math.cos(lat)*Math.cos(lon),cy+rad*Math.cos(lat)*Math.sin(lon),cz+rad*Math.sin(lat))}}
(0...n).each{|i|(0...n).each{|j| e.add_face(pts[i][j],pts[i][j+1],pts[i+1][j+1],pts[i+1][j]) rescue nil}}
mt=m.materials.add("m8");mt.color=Sketchup::Color.new(180,30,30);g.material=mt;m.commit_operation
''', "Sphere_Red")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="House_Tan";e=g.entities
x=585;y=280;w=55;d=55;h=40
f=e.add_face([x,y,0],[x+w,y,0],[x+w,y+d,0],[x,y+d,0]);f.pushpull(-h) if f
r1=Geom::Point3d.new(x+w/2.0,y,h+24);r2=Geom::Point3d.new(x+w/2.0,y+d,h+24)
e.add_face([x,y,h],[x+w,y,h],r1);e.add_face([x+w,y+d,h],[x,y+d,h],r2)
e.add_face([x,y,h],r1,r2,[x,y+d,h]);e.add_face([x+w,y,h],[x+w,y+d,h],r2,r1)
mt=m.materials.add("m9");mt.color=Sketchup::Color.new(210,190,150);g.material=mt;m.commit_operation
''', "House_Tan")

# === ROW 2 (middle, y=160) ===

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Pyramid_Red";e=g.entities
x=15;y=160;w=40;d=40;h=50;apex=Geom::Point3d.new(x+20,y+20,h)
e.add_face([x,y,0],[x+w,y,0],[x+w,y+d,0],[x,y+d,0])
e.add_face([x,y,0],[x+w,y,0],apex);e.add_face([x+w,y,0],[x+w,y+d,0],apex)
e.add_face([x+w,y+d,0],[x,y+d,0],apex);e.add_face([x,y+d,0],[x,y,0],apex)
mt=m.materials.add("m10");mt.color=Sketchup::Color.new(180,30,30);g.material=mt;m.commit_operation
''', "Pyramid_Red")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Star_Gold";e=g.entities
cx=105.0;cy=185.0;ro=25.0;ri=12.0
pts=(0...10).map{|i| a=Math::PI/5*i-Math::PI/2;r2=i.even? ? ro : ri
  Geom::Point3d.new(cx+r2*Math.cos(a),cy+r2*Math.sin(a),0)}
f=e.add_face(pts);f.pushpull(-30) if f
mt=m.materials.add("m11");mt.color=Sketchup::Color.new(220,170,40);g.material=mt;m.commit_operation
''', "Star_Gold")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="HexPrism_Brown";e=g.entities
cx=177.0;cy=182.0;rad=22.0
pts=(0...6).map{|i| a=Math::PI/3*i;Geom::Point3d.new(cx+rad*Math.cos(a),cy+rad*Math.sin(a),0)}
f=e.add_face(pts);f.pushpull(-55) if f
mt=m.materials.add("m12");mt.color=Sketchup::Color.new(160,130,90);g.material=mt;m.commit_operation
''', "HexPrism_Brown")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cone_Sm";e=g.entities
cx=242.0;cy=177.0;apex=Geom::Point3d.new(cx,cy,35)
c=e.add_circle([cx,cy,0],[0,0,1],12,24);e.add_face(c)
c.each{|ed| e.add_face(ed.start.position,ed.end.position,apex)}
mt=m.materials.add("m13");mt.color=Sketchup::Color.new(34,120,60);g.material=mt;m.commit_operation
''', "Cone_Sm_Green")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Diamond_Gold";e=g.entities
cx=312.0;cy=182.0
e.add_face([cx,cy-22,1],[cx+22,cy,1],[cx,cy+22,1],[cx-22,cy,1])
mt=m.materials.add("m14");mt.color=Sketchup::Color.new(220,170,40);g.material=mt;m.commit_operation
''', "Diamond_Gold")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="House_Blue";e=g.entities
x=355;y=160;w=60;d=50;h=40
f=e.add_face([x,y,0],[x+w,y,0],[x+w,y+d,0],[x,y+d,0]);f.pushpull(-h) if f
r1=Geom::Point3d.new(x+30,y,h+24);r2=Geom::Point3d.new(x+30,y+d,h+24)
e.add_face([x,y,h],[x+w,y,h],r1);e.add_face([x+w,y+d,h],[x,y+d,h],r2)
e.add_face([x,y,h],r1,r2,[x,y+d,h]);e.add_face([x+w,y,h],[x+w,y+d,h],r2,r1)
mt=m.materials.add("m15");mt.color=Sketchup::Color.new(25,50,100);g.material=mt;m.commit_operation
''', "House_Blue")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Hemisphere";e=g.entities
cx=462.0;cy=182.0;rad=22.0;n=12
pts=Array.new(n/2+1){|i| lat=Math::PI*i.to_f/n
  Array.new(n+1){|j| lon=2*Math::PI*j.to_f/n
    Geom::Point3d.new(cx+rad*Math.sin(lat)*Math.cos(lon),cy+rad*Math.sin(lat)*Math.sin(lon),rad*Math.cos(lat))}}
(0...pts.length-1).each{|i|(0...n).each{|j| e.add_face(pts[i][j],pts[i][j+1],pts[i+1][j+1],pts[i+1][j]) rescue nil}}
mt=m.materials.add("m16");mt.color=Sketchup::Color.new(180,180,185);g.material=mt;m.commit_operation
''', "Hemisphere_Silver")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Tube_Green";e=g.entities
cx=545.0;cy=185.0
co=e.add_circle([cx,cy,0],[0,0,1],25,24);fo=e.add_face(co);fo.pushpull(-45) if fo
ci=e.add_circle([cx,cy,0],[0,0,1],17,24);fi=e.add_face(ci);fi.pushpull(-45) if fi
mt=m.materials.add("m17");mt.color=Sketchup::Color.new(20,120,60);g.material=mt;m.commit_operation
''', "Tube_Green")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="TrunCone";e=g.entities
cx=622.0;cy=182.0;ro=22.0;ri=11.0;h=40;segs=24
bot=(0...segs).map{|i| a=2*Math::PI*i/segs;Geom::Point3d.new(cx+ro*Math.cos(a),cy+ro*Math.sin(a),0)}
top2=(0...segs).map{|i| a=2*Math::PI*i/segs;Geom::Point3d.new(cx+ri*Math.cos(a),cy+ri*Math.sin(a),h)}
e.add_face(bot);e.add_face(top2)
(0...segs).each{|i| j=(i+1)%segs;e.add_face(bot[i],bot[j],top2[j],top2[i])}
mt=m.materials.add("m18");mt.color=Sketchup::Color.new(210,180,170);g.material=mt;m.commit_operation
''', "TrunCone_Pink")

# === ROW 3 (front, y=40) ===

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Octahedron";e=g.entities
cx=50.0;cy=60.0;cz=25.0;s=20.0
tp=Geom::Point3d.new(cx,cy,cz+s);bt=Geom::Point3d.new(cx,cy,cz-s)
eq=[[cx+s,cy,cz],[cx,cy+s,cz],[cx-s,cy,cz],[cx,cy-s,cz]].map{|p| Geom::Point3d.new(*p)}
(0...4).each{|i| j=(i+1)%4;e.add_face(eq[i],eq[j],tp);e.add_face(eq[i],eq[j],bt)}
mt=m.materials.add("m19");mt.color=Sketchup::Color.new(180,160,50);g.material=mt;m.commit_operation
''', "Octahedron_Gold")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Torus";e=g.entities
cx=147.0;cy=67.0;cz=15.0;rr=18.0;tr=7.0;ns=16;nr=10
pts=Array.new(ns){|i| a=2*Math::PI*i.to_f/ns;Array.new(nr){|j| b=2*Math::PI*j.to_f/nr
  Geom::Point3d.new(cx+(rr+tr*Math.cos(b))*Math.cos(a),cy+(rr+tr*Math.cos(b))*Math.sin(a),cz+tr*Math.sin(b))}}
(0...ns).each{|i| ni=(i+1)%ns;(0...nr).each{|j| nj=(j+1)%nr;e.add_face(pts[i][j],pts[ni][j],pts[ni][nj],pts[i][nj]) rescue nil}}
mt=m.materials.add("m20");mt.color=Sketchup::Color.new(180,30,30);g.material=mt;m.commit_operation
''', "Torus_Red")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cross_Gold";e=g.entities
x=210;y=40;w=50;d=50;h=30;t=w/3.0
f1=e.add_face([x+t,y,0],[x+2*t,y,0],[x+2*t,y+d,0],[x+t,y+d,0]);f1.pushpull(-h) if f1
f2=e.add_face([x,y+t,0],[x+w,y+t,0],[x+w,y+2*t,0],[x,y+2*t,0]);f2.pushpull(-h) if f2
mt=m.materials.add("m21");mt.color=Sketchup::Color.new(220,170,40);g.material=mt;m.commit_operation
''', "Cross_Gold")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Pyramid_Tall";e=g.entities
x=300;y=40;w=35;d=35;h=70;apex=Geom::Point3d.new(x+17.5,y+17.5,h)
e.add_face([x,y,0],[x+w,y,0],[x+w,y+d,0],[x,y+d,0])
e.add_face([x,y,0],[x+w,y,0],apex);e.add_face([x+w,y,0],[x+w,y+d,0],apex)
e.add_face([x+w,y+d,0],[x,y+d,0],apex);e.add_face([x,y+d,0],[x,y,0],apex)
mt=m.materials.add("m22");mt.color=Sketchup::Color.new(34,120,60);g.material=mt;m.commit_operation
''', "Pyramid_Tall_Green")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Sphere_Blue";e=g.entities
cx=387.0;cy=57.0;cz=17.0;rad=17.0;n=12
pts=Array.new(n+1){|i| lat=Math::PI*i.to_f/n-Math::PI/2.0
  Array.new(n+1){|j| lon=2*Math::PI*j.to_f/n
    Geom::Point3d.new(cx+rad*Math.cos(lat)*Math.cos(lon),cy+rad*Math.cos(lat)*Math.sin(lon),cz+rad*Math.sin(lat))}}
(0...n).each{|i|(0...n).each{|j| e.add_face(pts[i][j],pts[i][j+1],pts[i+1][j+1],pts[i+1][j]) rescue nil}}
mt=m.materials.add("m23");mt.color=Sketchup::Color.new(25,50,100);g.material=mt;m.commit_operation
''', "Sphere_Blue")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Star_Red";e=g.entities
cx=450.0;cy=60.0;ro=20.0;ri=10.0
pts=(0...10).map{|i| a=Math::PI/5*i-Math::PI/2;r2=i.even? ? ro : ri
  Geom::Point3d.new(cx+r2*Math.cos(a),cy+r2*Math.sin(a),0)}
f=e.add_face(pts);f.pushpull(-25) if f
mt=m.materials.add("m24");mt.color=Sketchup::Color.new(180,30,30);g.material=mt;m.commit_operation
''', "Star_Red")

make_shape('''
m=Sketchup.active_model;m.start_operation('s',true);g=m.active_entities.add_group;g.name="Cylinder_Sm";e=g.entities
c=e.add_circle([517,57,0],[0,0,1],17,24);f=e.add_face(c);f.pushpull(-50) if f
mt=m.materials.add("m25");mt.color=Sketchup::Color.new(180,160,50);g.material=mt;m.commit_operation
''', "Cylinder_Sm")

# Camera + screenshot
print("\nPositioning camera...")
su.zoom_extents()
time.sleep(0.5)
su.set_camera(eye=(500, -250, 400), target=(300, 170, 20))
time.sleep(0.3)
path = su.take_screenshot("C:/su_capture/all_shapes.png")
print(f"Screenshot: {path}")
print("\nDONE! All 25 shapes created.")
