import { useCallback, useState } from "react";
import type { PromptTraceData } from "../../api/types";
import { getPromptTraceByRef } from "../../api/drama";

export interface PromptTraceRequest {
  refKey?: string;
  traceId?: string;
  label?: string;
  noPromptReason?: string;
}

export function usePromptTrace() {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<PromptTraceData | null>(null);
  const [request, setRequest] = useState<PromptTraceRequest | null>(null);

  const close = useCallback(() => {
    setOpen(false);
    setError(null);
    setTrace(null);
    setRequest(null);
  }, []);

  const openTrace = useCallback(async (req: PromptTraceRequest) => {
    setRequest(req);
    setOpen(true);
    setError(null);
    setTrace(null);

    if (req.noPromptReason) {
      return;
    }

    const refKey = req.refKey?.trim();
    if (!refKey) {
      setError("缺少 ref_key，无法反查 Prompt");
      return;
    }

    setLoading(true);
    try {
      const resp = await getPromptTraceByRef(refKey);
      if (!resp.success || !resp.data) {
        setError(resp.error ?? "未找到对应 Prompt 记录");
        return;
      }
      setTrace(resp.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载 Prompt 失败");
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    open,
    loading,
    error,
    trace,
    request,
    openTrace,
    close,
  };
}
