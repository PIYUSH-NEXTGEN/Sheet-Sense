import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "../api/client";
import type { GraphData } from "../api/types";
import { EmptyState, ErrorState, LoadingState } from "./States";
import { apiErrorMessage } from "../hooks/useWorkbook";

type FlowNode = Node<{ label: string; detail?: string; sheet?: string }>;

const X_GAP = 240;
const Y_GAP = 90;

/** Layered layout by longest-path depth (cycle-safe via bounded relaxation). */
function layout(data: GraphData): { nodes: FlowNode[]; edges: Edge[] } {
  const ids = data.nodes.map((node) => String(node["id"]));
  const incoming = new Map<string, string[]>();
  ids.forEach((id) => incoming.set(id, []));
  const edges: Edge[] = [];
  for (const edge of data.edges) {
    const source = String(edge.source);
    const target = String(edge.target);
    if (!incoming.has(source) || !incoming.has(target)) continue;
    incoming.get(target)?.push(source);
    edges.push({ id: `${source}→${target}`, source, target });
  }
  const depth = new Map<string, number>(ids.map((id) => [id, 0]));
  for (let round = 0; round < ids.length; round++) {
    for (const id of ids) {
      for (const source of incoming.get(id) ?? []) {
        depth.set(id, Math.max(depth.get(id) ?? 0, (depth.get(source) ?? 0) + 1));
      }
    }
  }
  const lanes = new Map<number, number>();
  const nodes: FlowNode[] = data.nodes.map((raw) => {
    const id = String(raw["id"]);
    const layer = depth.get(id) ?? 0;
    const row = lanes.get(layer) ?? 0;
    lanes.set(layer, row + 1);
    const kind = String(raw["type"] ?? "sheet");
    const label =
      kind === "group"
        ? `${String(raw["sheet"])} (${(raw["cells"] as string[]).length})`
        : kind === "more"
          ? `+${String(raw["count"] ?? "?")} cells`
          : id;
    const detail =
      kind === "group"
        ? String(raw["sample_formula"] ?? "")
        : raw["address"] != null
          ? `${String(raw["sheet"])}!${String(raw["address"])}`
          : [
              raw["formulas"] != null ? `${String(raw["formulas"])} formulas` : null,
              raw["inputs"] != null ? `${String(raw["inputs"])} inputs` : null,
            ]
              .filter(Boolean)
              .join(", ");
    return {
      id,
      position: { x: layer * X_GAP, y: row * Y_GAP },
      data: {
        label,
        detail,
        sheet: typeof raw["sheet"] === "string" ? raw["sheet"] : undefined,
      },
    };
  });
  return { nodes, edges };
}

/** Sheet-level dependency map (static; interactions are locked). */
export function DependencyGraph({ workbookId }: { workbookId: string }) {
  const navigate = useNavigate();
  const graph = useQuery({
    queryKey: ["graph", workbookId, "sheet"],
    queryFn: () => api.getGraph(workbookId, "sheet"),
    retry: 1,
  });
  const laid = useMemo(
    () => (graph.isSuccess ? layout(graph.data) : null),
    [graph.isSuccess, graph.data],
  );

  return (
    <div className="space-y-2">
      {graph.isPending && <LoadingState what="dependency map" />}
      {graph.isError && (
        <ErrorState
          message={apiErrorMessage(graph.error)}
          onRetry={() => graph.refetch()}
        />
      )}
      {laid && laid.nodes.length === 0 && (
        <EmptyState message="No dependencies to map." />
      )}
      {laid && laid.nodes.length > 0 && (
        <div className="h-[480px] overflow-hidden rounded-lg border border-night-600 bg-night-950">
          <ReactFlow
            nodes={laid.nodes}
            edges={laid.edges}
            fitView
            minZoom={0.2}
            colorMode="dark"
            zoomOnScroll={false}
            zoomOnPinch={false}
            zoomOnDoubleClick={false}
            panOnScroll={false}
            panOnDrag={false}
            nodesDraggable={false}
            nodesConnectable={false}
            onNodeClick={(_event, node) => {
              const sheet = (node.data as { sheet?: string }).sheet;
              if (sheet) {
                void navigate(
                  `/w/${workbookId}/sheets/${encodeURIComponent(sheet)}`,
                );
              }
            }}
          >
            <Background variant={BackgroundVariant.Dots} gap={24} />
          </ReactFlow>
        </div>
      )}
    </div>
  );
}
