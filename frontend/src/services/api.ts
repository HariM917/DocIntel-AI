import axios from 'axios';
import {
  AuthResponse,
  User,
  DocumentItem,
  DashboardStats,
  RecentDocumentItem,
  SecurityRule,
  ChatResponse,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const client = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT token to all requests if present
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('docintel_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 unauth
client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clear token if invalid
      if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
        localStorage.removeItem('docintel_token');
        localStorage.removeItem('docintel_user');
      }
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (email: string, password: string):Promise<AuthResponse> => {
    const res = await client.post<AuthResponse>('/auth/login', { email, password });
    return res.data;
  },
  register: async (email: string, password: string, full_name: string): Promise<AuthResponse> => {
    const res = await client.post<AuthResponse>('/auth/register', { email, password, full_name });
    return res.data;
  },
  getMe: async (): Promise<User> => {
    const res = await client.get<User>('/auth/me');
    return res.data;
  },
};

export const documentApi = {
  process: async (file: File, onUploadProgress?: (progressEvent: any) => void): Promise<DocumentItem> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await client.post<DocumentItem>('/documents/process', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress,
    });
    return res.data;
  },
  list: async (params?: { type?: string; status?: string; search?: string; page?: number; limit?: number }) => {
    const res = await client.get<{ documents: DocumentItem[]; total: number; page: number; limit: number }>(
      '/documents',
      { params }
    );
    return res.data;
  },
  get: async (documentId: string): Promise<DocumentItem> => {
    const res = await client.get<DocumentItem>(`/documents/${documentId}`);
    return res.data;
  },
  delete: async (documentId: string): Promise<void> => {
    await client.delete(`/documents/${documentId}`);
  },
  getDownloadUrl: (documentId: string) => `${API_BASE_URL}/api/documents/${documentId}/download`,
};

export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    const res = await client.get<DashboardStats>('/dashboard/stats');
    return res.data;
  },
  getRecent: async (): Promise<RecentDocumentItem[]> => {
    const res = await client.get<RecentDocumentItem[]>('/dashboard/recent');
    return res.data;
  },
};

export const searchApi = {
  query: async (q: string) => {
    const res = await client.get<{ query: string; total_matches: number; results: any[] }>('/search', {
      params: { q },
    });
    return res.data;
  },
};

export const securityApi = {
  getRules: async (): Promise<SecurityRule[]> => {
    const res = await client.get<SecurityRule[]>('/security/rules');
    return res.data;
  },
  updateRule: async (ruleId: string, data: Partial<SecurityRule>): Promise<SecurityRule> => {
    const res = await client.put<SecurityRule>(`/security/rules/${ruleId}`, data);
    return res.data;
  },
};

export const chatApi = {
  send: async (message: string, documentId?: string): Promise<ChatResponse> => {
    const res = await client.post<ChatResponse>('/chat', {
      message,
      document_id: documentId || null,
    });
    return res.data;
  },
};
