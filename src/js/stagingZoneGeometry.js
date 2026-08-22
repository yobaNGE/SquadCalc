export const STAGING_THIN_AXIS_RATIO = 0.5;

export function classifyStagingBox(box) {
    const { extent_x: x, extent_y: y, extent_z: z } = box.boxExtent;
    const [[smallestAxis, smallest], [, second]] = Object.entries({ x, y, z }).sort((a, b) => a[1] - b[1]);

    if (smallest / second >= STAGING_THIN_AXIS_RATIO) return "volume";
    return smallestAxis === "z" ? "horizontal" : "wall";
}

function rotatePoint(x, y, angle) {
    const radians = angle * Math.PI / 180;
    return [x * Math.cos(radians) - y * Math.sin(radians), x * Math.sin(radians) + y * Math.cos(radians)];
}

export function createStagingBoxPrimitive(box) {
    const { extent_x: x, extent_y: y, rotation_z: rotation = 0 } = box.boxExtent;

    return {
        type: "volume",
        points: [[-x, -y], [x, -y], [x, y], [-x, y]].map(([localX, localY]) => {
            const [dx, dy] = rotatePoint(localX, localY, rotation);
            return [box.location_x + dx, box.location_y + dy];
        })
    };
}

function normalizedOrientation(rotation) {
    return ((rotation % 90) + 90) % 90;
}

function boundsInOrientation(box, orientation) {
    const radians = -orientation * Math.PI / 180;
    const cosine = Math.cos(radians);
    const sine = Math.sin(radians);
    const points = createStagingBoxPrimitive(box).points.map(([x, y]) =>
        [x * cosine - y * sine, x * sine + y * cosine]);
    return {
        left: Math.min(...points.map(point => point[0])),
        right: Math.max(...points.map(point => point[0])),
        bottom: Math.min(...points.map(point => point[1])),
        top: Math.max(...points.map(point => point[1]))
    };
}

function touching(first, second) {
    const overlapX = Math.min(first.right, second.right) - Math.max(first.left, second.left);
    const overlapY = Math.min(first.top, second.top) - Math.max(first.bottom, second.bottom);
    return overlapX >= 0 && overlapY >= 0 && (overlapX > 0 || overlapY > 0);
}

function unionBoundary(rectangles, orientation) {
    const xs = [...new Set(rectangles.flatMap(rectangle => [rectangle.left, rectangle.right]))].sort((a, b) => a - b);
    const ys = [...new Set(rectangles.flatMap(rectangle => [rectangle.bottom, rectangle.top]))].sort((a, b) => a - b);
    const filled = Array.from({ length: xs.length - 1 }, () => Array(ys.length - 1).fill(false));

    for (let x = 0; x < xs.length - 1; x++) {
        for (let y = 0; y < ys.length - 1; y++) {
            const centerX = (xs[x] + xs[x + 1]) / 2;
            const centerY = (ys[y] + ys[y + 1]) / 2;
            filled[x][y] = rectangles.some(rectangle => centerX > rectangle.left && centerX < rectangle.right &&
                centerY > rectangle.bottom && centerY < rectangle.top);
        }
    }

    const edges = new Map();
    const addEdge = (start, end) => edges.set(start.join(","), end);
    for (let x = 0; x < xs.length - 1; x++) {
        for (let y = 0; y < ys.length - 1; y++) {
            if (!filled[x][y]) continue;
            if (!filled[x][y - 1]) addEdge([xs[x], ys[y]], [xs[x + 1], ys[y]]);
            if (!filled[x + 1]?.[y]) addEdge([xs[x + 1], ys[y]], [xs[x + 1], ys[y + 1]]);
            if (!filled[x][y + 1]) addEdge([xs[x + 1], ys[y + 1]], [xs[x], ys[y + 1]]);
            if (!filled[x - 1]?.[y]) addEdge([xs[x], ys[y + 1]], [xs[x], ys[y]]);
        }
    }

    const rings = [];
    while (edges.size) {
        const [startKey, firstEnd] = edges.entries().next().value;
        const start = startKey.split(",").map(Number);
        const ring = [start];
        let end = firstEnd;
        edges.delete(startKey);
        while (end[0] !== start[0] || end[1] !== start[1]) {
            ring.push(end);
            const key = end.join(",");
            end = edges.get(key);
            edges.delete(key);
        }
        rings.push(ring.filter((point, index) => {
            const previous = ring[(index - 1 + ring.length) % ring.length];
            const next = ring[(index + 1) % ring.length];
            return (point[0] - previous[0]) * (next[1] - point[1]) !==
                (point[1] - previous[1]) * (next[0] - point[0]);
        }));
    }

    const radians = orientation * Math.PI / 180;
    const cosine = Math.cos(radians);
    const sine = Math.sin(radians);
    return rings.map(ring => ring.map(([x, y]) => [x * cosine - y * sine, x * sine + y * cosine]));
}

export function mergeTouchingStagingBoxes(boxes) {
    const items = boxes.map(box => {
        const orientation = normalizedOrientation(box.boxExtent.rotation_z || 0);
        return { box, orientation, bounds: boundsInOrientation(box, orientation) };
    });
    const parents = items.map((_, index) => index);
    const root = index => parents[index] === index ? index : parents[index] = root(parents[index]);

    for (let first = 0; first < items.length; first++) {
        for (let second = first + 1; second < items.length; second++) {
            if (Math.abs(items[first].orientation - items[second].orientation) > 0.01 ||
                !touching(items[first].bounds, items[second].bounds)) continue;
            parents[root(second)] = root(first);
        }
    }

    const components = new Map();
    items.forEach((item, index) => {
        const key = root(index);
        if (!components.has(key)) components.set(key, []);
        components.get(key).push(item);
    });

    return [...components.values()].map(component => {
        const rings = unionBoundary(component.map(item => item.bounds), component[0].orientation);
        return { type: "volume", points: rings[0], rings };
    });
}
