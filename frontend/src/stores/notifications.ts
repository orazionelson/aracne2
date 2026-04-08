import { defineStore } from "pinia";
import { ref } from "vue";
import { apiClient } from "@/services/api";

export interface NotificationInfo {
  id: number;
  type: string;
  title: string;
  body: string | null;
  link: string | null;
  is_read: boolean;
  created_at: string;
  read_at: string | null;
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

export const useNotificationStore = defineStore("notifications", () => {
  const notifications = ref<NotificationInfo[]>([]);
  const pagination = ref<Pagination | null>(null);
  const unreadCount = ref(0);
  const isLoading = ref(false);

  async function fetchUnreadCount(): Promise<void> {
    unreadCount.value = await apiClient.get<number>("/notifications/unread-count");
  }

  async function fetchNotifications(page = 1, unreadOnly = false): Promise<void> {
    isLoading.value = true;
    try {
      const res = await apiClient.getPaginated<NotificationInfo>("/notifications", {
        params: { page, per_page: 20, unread_only: unreadOnly },
      });
      notifications.value = res.data as NotificationInfo[];
      pagination.value = res.pagination as Pagination;
    } finally {
      isLoading.value = false;
    }
  }

  async function markRead(id: number): Promise<void> {
    await apiClient.patch<NotificationInfo>(`/notifications/${id}/read`);
    const item = notifications.value.find((n) => n.id === id);
    if (item) item.is_read = true;
    if (unreadCount.value > 0) unreadCount.value--;
  }

  async function markAllRead(): Promise<void> {
    await apiClient.post<number>("/notifications/read-all");
    notifications.value.forEach((n) => (n.is_read = true));
    unreadCount.value = 0;
  }

  async function removeNotification(id: number): Promise<void> {
    await apiClient.delete<void>(`/notifications/${id}`);
    const idx = notifications.value.findIndex((n) => n.id === id);
    if (idx !== -1) {
      const wasUnread = !notifications.value[idx].is_read;
      notifications.value.splice(idx, 1);
      if (wasUnread && unreadCount.value > 0) unreadCount.value--;
    }
  }

  function reset(): void {
    notifications.value = [];
    pagination.value = null;
    unreadCount.value = 0;
  }

  return {
    notifications,
    pagination,
    unreadCount,
    isLoading,
    fetchUnreadCount,
    fetchNotifications,
    markRead,
    markAllRead,
    removeNotification,
    reset,
  };
});
