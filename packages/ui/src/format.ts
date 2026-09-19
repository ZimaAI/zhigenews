export function formatDate(value: string | null | undefined, time = false): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    ...(time ? { hour: '2-digit' as const, minute: '2-digit' as const, second: '2-digit' as const } : {}),
  }).format(date);
}

export function statusLabel(status: string): string {
  return ({
    queued: '排队中', running: '运行中', completed: '已完成', partial: '部分完成',
    failed: '失败', cancelling: '正在取消', cancelled: '已取消', pending: '待发布',
    submitted: '已发布', unknown: '状态未知', healthy: '正常', syncing: '采集中',
    disabled: '已停用', unverified: '未验证', enabled: '已启用', active: '正常',
    blocked: '已封禁', published: '已发布', draft: '草稿', verified: '已验证',
    success: '成功', error: '失败', unavailable: '不可用', skipped: '未执行',
  } as Record<string, string>)[status] ?? status;
}

export function formatMetric(value: number | null | undefined, digits = 1): string {
  return value == null ? '—' : value.toLocaleString('zh-CN', { maximumFractionDigits: digits });
}
