import { useEffect, useMemo, useRef, useState } from "react";
import type Konva from "konva";
import {
  Circle,
  Image as KonvaImage,
  Layer,
  Line,
  Rect as KonvaRect,
  Stage,
  Transformer,
} from "react-konva";
import type { PoseSkeleton, Rect } from "../types";

interface Props {
  imageUrl: string;
  bbox: Rect;
  onBboxChange: (bbox: Rect) => void;
  skeleton: PoseSkeleton | null;
  onSkeletonChange: (skeleton: PoseSkeleton) => void;
  highlighted: Set<string>;
  fitToImage?: boolean;
}

const CONNECTIONS = [
  ["left_ankle", "left_knee"], ["left_knee", "left_hip"],
  ["right_ankle", "right_knee"], ["right_knee", "right_hip"],
  ["left_hip", "right_hip"], ["left_shoulder", "left_hip"],
  ["right_shoulder", "right_hip"], ["left_shoulder", "right_shoulder"],
  ["left_shoulder", "left_elbow"], ["left_elbow", "left_wrist"],
  ["right_shoulder", "right_elbow"], ["right_elbow", "right_wrist"],
  ["left_eye", "right_eye"], ["nose", "left_eye"], ["nose", "right_eye"],
  ["left_eye", "left_ear"], ["right_eye", "right_ear"],
  ["left_ear", "left_shoulder"], ["right_ear", "right_shoulder"],
] as const;

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

export default function PoseCanvas({
  imageUrl,
  bbox,
  onBboxChange,
  skeleton,
  onSkeletonChange,
  highlighted,
  fitToImage = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bboxRef = useRef<Konva.Rect>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const [size, setSize] = useState({ width: 560, height: 480 });
  const [image, setImage] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observedNode = fitToImage ? node.parentElement ?? node : node;
    const resize = () => {
      if (fitToImage && image) {
        const availableWidth = Math.max(220, observedNode.clientWidth);
        const imageRatio = image.width / image.height;
        const maximumHeight = Math.min(
          620,
          Math.max(420, window.innerHeight * 0.6),
        );
        const width = Math.min(availableWidth, maximumHeight * imageRatio);
        setSize({ width, height: width / imageRatio });
        return;
      }
      setSize({
        width: Math.max(280, node.clientWidth),
        height: Math.max(340, node.clientHeight),
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(observedNode);
    window.addEventListener("resize", resize);
    resize();
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", resize);
    };
  }, [fitToImage, image]);

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
    return {
      x: (size.width - width) / 2,
      y: (size.height - height) / 2,
      width,
      height,
    };
  }, [image, size]);

  useEffect(() => {
    const transformer = transformerRef.current;
    transformer?.nodes(!skeleton && bboxRef.current ? [bboxRef.current] : []);
    transformer?.getLayer()?.batchDraw();
  }, [skeleton, bbox, frame]);

  const normalizeBox = (node: Konva.Rect): Rect => {
    const scaleX = node.scaleX();
    const scaleY = node.scaleY();
    node.scale({ x: 1, y: 1 });
    const width = clamp((node.width() * scaleX) / frame.width, 0.08, 1);
    const height = clamp((node.height() * scaleY) / frame.height, 0.08, 1);
    return {
      x: clamp((node.x() - frame.x) / frame.width, 0, 1 - width),
      y: clamp((node.y() - frame.y) / frame.height, 0, 1 - height),
      width,
      height,
    };
  };

  const pointMap = new Map(skeleton?.keypoints.map((point) => [point.name, point]));
  const movePoint = (name: string, x: number, y: number) => {
    if (!skeleton) return;
    onSkeletonChange({
      ...skeleton,
      confirmed: false,
      keypoints: skeleton.keypoints.map((point) =>
        point.name === name
          ? {
              ...point,
              x: clamp((x - frame.x) / frame.width, 0, 1),
              y: clamp((y - frame.y) / frame.height, 0, 1),
              confidence: 1,
              source: "user",
              visibility: "visible",
            }
          : point,
      ),
    });
  };

  return (
    <div
      className={`pose-canvas ${fitToImage ? "fit-to-image" : ""}`}
      ref={containerRef}
      style={fitToImage ? { width: size.width, height: size.height } : undefined}
    >
      <Stage width={size.width} height={size.height}>
        <Layer>
          <KonvaRect width={size.width} height={size.height} fill="#181817" />
          {image && <KonvaImage image={image} {...frame} />}
          {!skeleton && (
            <>
              <KonvaRect
                ref={bboxRef}
                x={frame.x + bbox.x * frame.width}
                y={frame.y + bbox.y * frame.height}
                width={bbox.width * frame.width}
                height={bbox.height * frame.height}
                stroke="#ff765f"
                strokeWidth={2}
                fill="rgba(255,118,95,.09)"
                draggable
                onDragEnd={(event) => onBboxChange(normalizeBox(event.target as Konva.Rect))}
                onTransformEnd={(event) => onBboxChange(normalizeBox(event.target as Konva.Rect))}
              />
              <Transformer
                ref={transformerRef}
                rotateEnabled={false}
                keepRatio={false}
                anchorFill="#fff"
                anchorStroke="#ff765f"
                anchorSize={10}
                borderEnabled={false}
                boundBoxFunc={(oldBox, nextBox) =>
                  nextBox.width < 45 || nextBox.height < 70 ? oldBox : nextBox
                }
              />
            </>
          )}
          {skeleton && CONNECTIONS.map(([from, to]) => {
            const first = pointMap.get(from);
            const second = pointMap.get(to);
            if (!first || !second || first.visibility === "hidden" || second.visibility === "hidden") return null;
            const warning = highlighted.has(from) || highlighted.has(to);
            return (
              <Line
                key={`${from}-${to}`}
                points={[
                  frame.x + first.x * frame.width,
                  frame.y + first.y * frame.height,
                  frame.x + second.x * frame.width,
                  frame.y + second.y * frame.height,
                ]}
                stroke={warning ? "#ff5b45" : "#63b3ff"}
                strokeWidth={warning ? 4 : 3}
                lineCap="round"
                opacity={0.9}
              />
            );
          })}
          {skeleton?.keypoints.map((point) => {
            if (point.visibility === "hidden") return null;
            const warning = highlighted.has(point.name);
            return (
              <Circle
                key={point.name}
                x={frame.x + point.x * frame.width}
                y={frame.y + point.y * frame.height}
                radius={warning ? 7 : 6}
                fill={warning ? "#ff5b45" : point.source === "user" ? "#f9c74f" : "#fff"}
                stroke="#171716"
                strokeWidth={2}
                draggable
                onDragMove={(event) => movePoint(point.name, event.target.x(), event.target.y())}
              />
            );
          })}
        </Layer>
      </Stage>
      <span className="pose-canvas-hint">
        {skeleton ? "Drag joints to correct the skeleton" : "Frame one person, then estimate"}
      </span>
    </div>
  );
}
