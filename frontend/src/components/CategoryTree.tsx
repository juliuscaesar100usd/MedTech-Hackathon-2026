import { useState, type ReactNode } from 'react';
import type { TreeNode } from '../lib/api';

// Indentation geometry (px). Each deeper level shifts right by INDENT_STEP.
const INDENT_BASE = 12;
const INDENT_STEP = 18;

/** Total number of leaf services in a node's entire subtree. */
export function countLeaves<Leaf>(node: TreeNode<Leaf>): number {
  let n = node.services.length;
  for (const child of node.children) n += countLeaves(child);
  return n;
}

/**
 * Prune a tree down to the nodes/leaves whose leaves satisfy `predicate`.
 * A node is kept when it has any matching leaf directly or in any descendant.
 * Returns a new tree (input is never mutated) — handy for client-side search.
 */
export function filterTree<Leaf>(
  nodes: TreeNode<Leaf>[],
  predicate: (leaf: Leaf) => boolean,
): TreeNode<Leaf>[] {
  const out: TreeNode<Leaf>[] = [];
  for (const node of nodes) {
    const services = node.services.filter(predicate);
    const children = filterTree(node.children, predicate);
    if (services.length || children.length) {
      out.push({ ...node, services, children });
    }
  }
  return out;
}

export interface CategoryTreeProps<Leaf> {
  /** Top-level nodes of the taxonomy. */
  nodes: TreeNode<Leaf>[];
  /** Render-prop for a leaf service (catalog service, partner price row, …). */
  renderLeaf: (leaf: Leaf) => ReactNode;
  /** Optional stable React key for a leaf (falls back to its index). */
  leafKey?: (leaf: Leaf, index: number) => string | number;
  /** Levels expanded by default: nodes at depth < this start open. Default 1. */
  defaultExpandedDepth?: number;
}

/**
 * A reusable, generic, N-level collapsible category tree (2GIS-style price
 * catalogue: "Лаборатория" → "Анализ крови" → "Гормоны" → "ТТГ"). Nodes toggle
 * on click with a chevron and show a count badge of the leaves in their subtree.
 */
export function CategoryTree<Leaf>({
  nodes,
  renderLeaf,
  leafKey,
  defaultExpandedDepth = 1,
}: CategoryTreeProps<Leaf>) {
  if (!nodes || nodes.length === 0) return null;
  return (
    <ul className="cat-tree" role="tree">
      {nodes.map((node, i) => (
        <TreeBranch
          key={node.path.join(' › ') || `${node.name}-${i}`}
          node={node}
          depth={0}
          renderLeaf={renderLeaf}
          leafKey={leafKey}
          defaultExpandedDepth={defaultExpandedDepth}
        />
      ))}
    </ul>
  );
}

function TreeBranch<Leaf>({
  node,
  depth,
  renderLeaf,
  leafKey,
  defaultExpandedDepth,
}: {
  node: TreeNode<Leaf>;
  depth: number;
  renderLeaf: (leaf: Leaf) => ReactNode;
  leafKey?: (leaf: Leaf, index: number) => string | number;
  defaultExpandedDepth: number;
}) {
  const [open, setOpen] = useState(depth < defaultExpandedDepth);
  const count = countLeaves(node);
  const hasChildren = node.children.length > 0 || node.services.length > 0;
  const togglePad = INDENT_BASE + depth * INDENT_STEP;
  const leafPad = INDENT_BASE + (depth + 1) * INDENT_STEP;

  return (
    <li className="cat-node" role="treeitem" aria-expanded={open}>
      <button
        type="button"
        className="cat-node-toggle"
        style={{ paddingLeft: togglePad }}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={`cat-chevron${open ? ' open' : ''}`} aria-hidden="true">
          ▸
        </span>
        <span className="cat-node-name">{node.name}</span>
        <span className="cat-count" aria-label={`${count} services`}>
          {count}
        </span>
      </button>

      {open && hasChildren && (
        <div className="cat-node-body">
          {node.children.length > 0 && (
            <ul className="cat-children" role="group">
              {node.children.map((child, i) => (
                <TreeBranch
                  key={child.path.join(' › ') || `${child.name}-${i}`}
                  node={child}
                  depth={depth + 1}
                  renderLeaf={renderLeaf}
                  leafKey={leafKey}
                  defaultExpandedDepth={defaultExpandedDepth}
                />
              ))}
            </ul>
          )}
          {node.services.length > 0 && (
            <ul className="cat-leaves" role="group">
              {node.services.map((leaf, i) => (
                <li
                  key={leafKey ? leafKey(leaf, i) : i}
                  className="cat-leaf-item"
                  style={{ paddingLeft: leafPad }}
                >
                  {renderLeaf(leaf)}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}
