import { useEffect, useMemo, useRef, useState } from "react";
import { Image as KonvaImage, Layer, Rect as KonvaRect, Stage, Text, Transformer } from "react-konva";
import type Konva from "konva";
import type { Rect, Suggestion } from "../types";

interface Props {
  imageUrl: string;
  suggestions: Suggestion[];
  activeId: string | null;
  onActiveChange: (id: string) => void;
  onRegionChange: (id: string, region: Rect) => void;
}

const COLORS = ["#ff5b45", "#3977ff", "#7a55d8"];

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export default function AnnotationCanvas({
  imageUrl,
  suggestions,
  activeId,
  onActiveChange,
  onRegionChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const shapeRefs = useRef<Record<string, Konva.Rect | null>>({});
  const [size, setSize] = useState({ width: 800, height: 620 });
  const [image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(320, entry.contentRect.width);
      const height = Math.max(420, entry.contentRect.height);
      setSize({ width, height });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const next = new window.Image();
    next.crossOrigin = "anonymous";
    next.onload = () => setImage(next);
    next.src = imageUrl;
  }, [imageUrl]);

  const frame = useMemo(() => {
    if (!image) return { x: 0, y: 0, width: size.width, height: size.height };
    const scale = Math.min(size.width / image.width, size.height / image.height);
    const width = image.width * scale;
    const height = image.height * scale;
    return { x: (size.width - width) / 2, y: (size.height - height) / 2, width, height };
  }, [image, size]);

  useEffect(() => {
    const transformer = transformerRef.current;
    if (!transformer) return;
    const active = activeId ? shapeRefs.current[activeId] : null;
    transformer.nodes(active ? [active] : []);
    transformer.getLayer()?.batchDraw();
  }, [activeId, suggestions]);

  const normalizedRegion = (node: Konva.Rect): Rect => {
    const scaleX = node.scaleX();
    const scaleY = node.scaleY();
    node.scaleX(1);
    node.scaleY(1);
    const width = clamp((node.width() * scaleX) / frame.width, 0.04, 1);
    const height = clamp((node.height() * scaleY) / frame.height, 0.04, 1);
    const x = clamp((node.x() - frame.x) / frame.width, 0, 1 - width);
    const y = clamp((node.y() - frame.y) / frame.height, 0, 1 - height);
    return { x, y, width, height };
  };

  return (
    <div className="canvas-shell" ref={containerRef}>
      <Stage width={size.width} height={size.height}>
        <Layer>
          <KonvaRect x={0} y={0} width={size.width} height={size.height} fill="#181817" />
          {image && <KonvaImage image={image} {...frame} />}
          {suggestions.map((suggestion, index) => {
            const region = suggestion.region;
            const color = COLORS[index % COLORS.length];
            return (
              <KonvaRect
                key={suggestion.id}
                ref={(node) => {
                  shapeRefs.current[suggestion.id] = node;
                }}
                x={frame.x + region.x * frame.width}
                y={frame.y + region.y * frame.height}
                width={region.width * frame.width}
                height={region.height * frame.height}
                fill={`${color}22`}
                stroke={color}
                strokeWidth={activeId === suggestion.id ? 3 : 2}
                cornerRadius={8}
                draggable
                dragBoundFunc={(position) => ({
                  x: clamp(position.x, frame.x, frame.x + frame.width - region.width * frame.width),
                  y: clamp(position.y, frame.y, frame.y + frame.height - region.height * frame.height),
                })}
                onClick={() => onActiveChange(suggestion.id)}
                onTap={() => onActiveChange(suggestion.id)}
                onDragEnd={(event) => onRegionChange(suggestion.id, normalizedRegion(event.target as Konva.Rect))}
                onTransformEnd={(event) => onRegionChange(suggestion.id, normalizedRegion(event.target as Konva.Rect))}
              />
            );
          })}
          {suggestions.map((suggestion, index) => (
            <Text
              key={`label-${suggestion.id}`}
              x={frame.x + suggestion.region.x * frame.width + 10}
              y={frame.y + suggestion.region.y * frame.height + 9}
              text={String(index + 1).padStart(2, "0")}
              fontFamily="Inter, system-ui, sans-serif"
              fontSize={13}
              fontStyle="bold"
              fill="#ffffff"
              listening={false}
            />
          ))}
          <Transformer
            ref={transformerRef}
            rotateEnabled={false}
            keepRatio={false}
            anchorFill="#ffffff"
            anchorStroke="#181817"
            anchorSize={10}
            borderEnabled={false}
            boundBoxFunc={(oldBox, newBox) =>
              newBox.width < 40 || newBox.height < 40 ? oldBox : newBox
            }
          />
        </Layer>
      </Stage>
      {suggestions.length > 0 && <div className="canvas-hint">Drag or resize a region to correct the AI annotation</div>}
    </div>
  );
}

