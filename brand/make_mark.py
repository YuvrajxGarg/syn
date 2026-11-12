import sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
f=TTFont('/usr/share/fonts/opentype/inter/InterDisplay-Black.otf')
upm=f['head'].unitsPerEm; gs=f.getGlyphSet(); cmap=f.getBestCmap(); hmtx=f['hmtx']
xh=f['OS/2'].sxHeight
E=upm  # 1em
x=0; paths=[]
for ch in 'syn':
    g=cmap[ord(ch)]; pen=SVGPathPen(gs)
    gs[g].draw(TransformPen(pen,(1,0,0,-1,x,0)))
    paths.append(pen.getCommands()); x+=hmtx[g][0]-0.055*E
# link: margin .09em after letter-spaced advance
lx=x+0.09*E; w=0.17*E; r=w/2; lw=0.062*E
cx=lx+r
top=-xh; bot=0
link=(f'<circle cx="{cx:.1f}" cy="{top+r:.1f}" r="{r:.1f}"/><circle cx="{cx:.1f}" cy="{bot-r:.1f}" r="{r:.1f}"/>'
      f'<rect x="{cx-lw/2:.1f}" y="{top+r:.1f}" width="{lw:.1f}" height="{(bot-r)-(top+r):.1f}" rx="{lw/2:.1f}"/>')
# bounds
bp=BoundsPen(gs); 
asc=f['OS/2'].sCapHeight
desc=-f['OS/2'].sTypoDescender
minY=-max(xh+40,  xh); 
# viewBox: tight on text: y from -(xh+overshoot) to descender of y
yb=BoundsPen(gs); gs[cmap[ord('y')]].draw(yb); ydesc=-yb.bounds[1]
sb=BoundsPen(gs); gs[cmap[ord('s')]].draw(sb); over=sb.bounds[3]
pad=0.04*E
vx=-pad; vy=-over-pad; vw=lx+w+2*pad; vh=over+ydesc+2*pad
def svg(text_fill, accent, cls=''):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.0f} {vy:.0f} {vw:.0f} {vh:.0f}" role="img" aria-label="Syn">'
        f'<g fill="{text_fill}"><path d="{" ".join(paths)}"/></g><g fill="{accent}">{link}</g></svg>\n')
open('mark.svg','w').write(svg('#ffffff','#ccff4d'))
open('mark-currentcolor.svg','w').write(svg('currentColor','#ccff4d'))
open('mark-dark.svg','w').write(svg('#0e0e10','#ccff4d'))
print('upm',upm,'xh',xh,'over',over,'ydesc',ydesc,'viewBox',vx,vy,vw,vh)
