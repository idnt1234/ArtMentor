import type { Locale } from "./locale";

// Existing pose records store English diagnostics. Localize known report messages at
// display time so a language switch never changes or reruns the underlying check.
const messages: Readonly<Record<string, string>> = {
  "The artwork and reference depict the intended same pose and person.": "作品和参考图应表现同一个人物和预期姿势。",
  "This is a 2D keypoint comparison; foreshortening and depth are not reconstructed.": "此对比基于二维关节点，不能重建透视缩短或深度。",
  "There is no reference image; findings indicate unusual 2D geometry, not anatomical proof.": "没有参考图。检查只提示二维几何关系的异常，不能作为解剖正确与否的证据。",
  "Strong foreshortening, hidden joints and perspective can explain left-right length differences.": "明显的透视缩短、关节遮挡和视角都可能造成左右长度不同。",
  "Confirm the artwork skeleton first": "请先确认作品骨架",
  "The detected joints have not been checked by the artist.": "检测出的关节点还未由创作者复核。",
  "A user-confirmed COCO-17 skeleton": "用户确认过的 COCO-17 骨架",
  "Self-check not run": "尚未运行自检",
  "Drag misplaced joints, mark hidden points, then confirm the skeleton.": "拖动放错的关节点，标记遮挡点，然后确认骨架。",
  "Too few reliable joints": "可靠的关节点过少",
  "At least 10 visible or user-corrected points": "至少 10 个可见或已手动校正的点",
  "Correct uncertain joints or mark genuinely hidden joints before retrying.": "重试前请校正不确定的关节点，并标记确实被遮挡的关节。",
  "If this is not strong foreshortening, move the shorter side's middle or end joint and recheck.": "如果没有明显的透视缩短，请校正较短一侧的中间或末端关节后再检查。",
  "Hip center falls outside the visible support span": "髋部中心超出可见支撑范围",
  "Static balance usually projects between or near the supporting feet.": "静态平衡时，重心的投影通常在两支撑脚之间或附近。",
  "If the pose is not falling or stepping, recheck the hip and ankle positions before redrawing the silhouette.": "如果人物没有在跌倒或迈步，重画轮廓前请先复核髋部和脚踝的位置。",
  "No large 2D skeleton inconsistency found": "未发现明显的二维骨架不一致",
  "Segment ratios, strong left-right differences and visible support alignment stay within broad tolerance.": "肢段比例、左右差异和可见的支撑对齐都在宽松容差内。",
  "Conservative no-reference checks": "保守的无参考图检查",
  "Within configured thresholds": "在设定阈值内",
  "Continue with volume, contour and foreshortening checks; COCO-17 joints cannot verify those properties.": "请继续检查体积、轮廓与透视缩短。COCO-17 关节点无法验证这些方面。",
  "Confirm both skeletons first": "请先确认两张图的骨架",
  "At least one skeleton is still unconfirmed.": "至少有一张图的骨架尚未确认。",
  "Both skeletons confirmed by the user": "两张图的骨架均由用户确认",
  "Comparison not run": "尚未运行对比",
  "Drag uncertain joints into place, mark hidden points, then confirm both sides.": "校正不确定的关节点，标记遮挡点，然后确认两张图的骨架。",
  "Correct low-confidence points or mark the genuinely hidden joints before retrying.": "重试前请校正低置信度的关节点，并标记确实被遮挡的关节。",
  "No large 2D skeleton discrepancy found": "未发现明显的二维骨架差异",
  "Comparable limb lengths, major joint bends, shoulder axis and hip axis stay within tolerance.": "可比较的四肢长度、主要关节弯曲度、肩轴和髋轴都在容差内。",
  "The user-confirmed reference skeleton": "用户确认过的参考骨架",
  "Inspect contour, volume and foreshortening separately; COCO-17 points cannot verify those properties.": "请单独检查轮廓、体积和透视缩短。COCO-17 关节点无法验证这些方面。",
  "Demo skeleton: no neural pose model was called.": "演示骨架：未调用姿态检测模型。",
  "This is one depth hypothesis inferred from a single image, not measured 3D ground truth.": "这是根据单张图推测的一种深度分布，未经过真实三维测量。",
  "A low 2D projection error only shows image-plane agreement; hidden depth can still be wrong.": "二维投影误差小只代表图像平面更贴合，被遮挡部分的深度仍可能不准确。",
  "Clothing, occlusion, stylization and unusual camera perspective can change the recovered surface.": "衣物、遮挡、画风和特殊视角都可能改变推测得到的表面形状。",
  "No anatomy diagnosis or correctness verdict is generated from this preview.": "此预览不会给出人体解剖诊断或正确性结论。",
};

const terms: Readonly<Record<string, string>> = {
  "left": "左",
  "right": "右",
  "long": "长",
  "short": "短",
  "longer": "更长",
  "shorter": "更短",
  "left arm": "左臂",
  "right arm": "右臂",
  "left leg": "左腿",
  "right leg": "右腿",
  "upper arms": "上臂",
  "forearms": "前臂",
  "thighs": "大腿",
  "lower legs": "小腿",
  "left upper arm": "左上臂",
  "right upper arm": "右上臂",
  "left forearm": "左前臂",
  "right forearm": "右前臂",
  "left thigh": "左大腿",
  "right thigh": "右大腿",
  "left lower leg": "左小腿",
  "right lower leg": "右小腿",
  "left elbow": "左肘",
  "right elbow": "右肘",
  "left wrist": "左腕",
  "right wrist": "右腕",
  "left knee": "左膝",
  "right knee": "右膝",
  "left ankle": "左踝",
  "right ankle": "右踝",
  "left hip": "左髋",
  "right hip": "右髋",
  "left shoulder": "左肩",
  "right shoulder": "右肩",
  "nose": "鼻尖",
  "left eye": "左眼",
  "right eye": "右眼",
  "left ear": "左耳",
  "right ear": "右耳",
  "shoulder axis": "肩轴",
  "hip axis": "髋轴",
  "realistic": "写实",
  "semi realistic": "半写实",
  "stylized": "风格化",
  "intentional distortion": "有意变形",
};

const term = (value: string) => {
  const key = value.toLowerCase().replaceAll("_", " ");
  return Object.hasOwn(terms, key) ? terms[key] : value;
};

const patterns: [RegExp, (...parts: string[]) => string][] = [
  [/^Only (\d+) of 17 points are available\.$/, (count) => `17 个关节点中只有 ${count} 个可用。`],
  [/^Only (\d+) of 17 points can be compared\.$/, (count) => `17 个关节点中只有 ${count} 个可比较。`],
  [/^(\d+) points missing$/, (count) => `还缺 ${count} 个关节点`],
  [/^Tolerance uses the (.+) profile\.$/, (profile) => `容差采用「${term(profile)}」设置。`],
  [/^(.+) segment ratio is unusual$/, (limb) => `${term(limb)}的肢段比例偏离较大`],
  [/^Outer\/inner segment ratio: (.+)$/, (ratio) => `远端与近端肢段长度比：${ratio}`],
  [/^Broad 2D tolerance under this style: (.+)$/, (range) => `当前画风的宽松二维容差：${range}`],
  [/^Outer segment appears relatively (long|short)$/, (size) => `远端肢段相对偏${term(size)}`],
  [/^Recheck the (.+) position before changing the contour\.$/, (joint) => `调整轮廓前，请复核${term(joint)}的位置。`],
  [/^Projected (.+) differ strongly$/, (limbs) => `左右${term(limbs)}的投影长度差异明显`],
  [/^Longer\/shorter projected length ratio: (.+)$/, (ratio) => `较长与较短的投影长度比：${ratio}`],
  [/^Review threshold for this style: (.+)$/, (threshold) => `当前画风的复核阈值：${threshold}`],
  [/^The (left|right) side is much shorter in 2D$/, (side) => `${term(side)}侧在二维平面上明显更短`],
  [/^Hip center sits (.+) image widths beyond the (left|right) ankle span\.$/, (offset, side) => `髋部中心向${term(side)}超出脚踝支撑范围，约为图像宽度的 ${offset} 倍。`],
  [/^Weight projects to the (left|right)$/, (side) => `重心投影偏向${term(side)}侧`],
  [/^(.+) bend differs from the reference$/, (joint) => `${term(joint)}弯曲度与参考图不同`],
  [/^(.+) tilt differs from the reference$/, (axis) => `${term(axis)}倾斜角与参考图不同`],
  [/^(.+) differs from the reference$/, (part) => `${term(part)}与参考图不同`],
  [/^Artwork normalized length: (.+) torso units$/, (length) => `作品中的归一化长度：躯干长度的 ${length} 倍`],
  [/^Reference normalized length: (.+) torso units$/, (length) => `参考图中的归一化长度：躯干长度的 ${length} 倍`],
  [/^(\d+)% (longer|shorter)$/, (value, direction) => `${term(direction)} ${value}%`],
  [/^Move the (.+) toward the reference direction, then re-check the silhouette\.$/, (part) => `向参考方向移动${term(part)}，再核对轮廓。`],
  [/^Artwork joint angle: (.+)$/, (angle) => `作品关节角度：${angle}`],
  [/^Reference joint angle: (.+)$/, (angle) => `参考图关节角度：${angle}`],
  [/^Adjust the (.+) or adjacent endpoint to match the intended bend\.$/, (joint) => `调整${term(joint)}或相邻端点，使其符合预期弯曲度。`],
  [/^Artwork tilt: (.+)$/, (angle) => `作品倾斜角：${angle}`],
  [/^Reference tilt: (.+)$/, (angle) => `参考图倾斜角：${angle}`],
  [/^Rotate the (.+) around its midpoint while preserving the intended gesture\.$/, (axis) => `以中点为轴旋转${term(axis)}，同时保留预期的动作。`],
  [/^Low-confidence points: (.+)$/, (names) => `低置信度关节点：${names.split(", ").map(term).join("、")}`],
];

export function translatePoseText(locale: Locale, message: string): string {
  if (locale !== "zh-CN") return message;
  if (Object.hasOwn(messages, message)) return messages[message];
  for (const [pattern, format] of patterns) {
    const match = pattern.exec(message);
    if (match) return format(...match.slice(1));
  }
  return message;
}
