import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Bot,
  Send,
  User,
  Sparkles,
  FileText,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  ExternalLink,
  Search,
} from 'lucide-react';
import { chatApi, documentApi } from '../services/api';
import { ChatResponse, SourceReference } from '../types';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  sources?: SourceReference[];
  confidence?: number;
  timestamp: string;
}

const SAMPLE_QUESTIONS = [
  'What is the invoice amount?',
  'Who is the vendor?',
  'Which documents contain Aadhaar numbers?',
  'What is the term and governing law in the contract?',
  'Show me active security rules and redaction status.',
];

export const AIAssistant: React.FC = () => {
  const location = useLocation();
  const initialDocId = (location.state as any)?.initialDocId || '';

  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello! I am your DocIntel AI Assistant. I can answer questions grounded strictly on your processed enterprise documents, retrieve financial amounts, identify vendors, and track sensitive PII compliance.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [inputQuery, setInputQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState<string>(initialDocId);
  const [documents, setDocuments] = useState<{ document_id: string; filename: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<string, boolean>>({});

  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchDocList = async () => {
      try {
        const data = await documentApi.list({ limit: 100 });
        setDocuments(data.documents.map((d) => ({ document_id: d.document_id, filename: d.filename })));
      } catch (err) {
        console.error('Failed to load document list for filter:', err);
      }
    };
    fetchDocList();
  }, []);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async (queryText?: string) => {
    const q = (queryText || inputQuery).trim();
    if (!q || loading) return;

    const userMsg: Message = {
      id: Math.random().toString(36).substring(2, 9),
      sender: 'user',
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuery('');
    setLoading(true);

    try {
      const response: ChatResponse = await chatApi.send(q, selectedDocId || undefined);

      const assistantMsg: Message = {
        id: Math.random().toString(36).substring(2, 9),
        sender: 'assistant',
        text: response.answer,
        sources: response.sources,
        confidence: response.confidence,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: Message = {
        id: Math.random().toString(36).substring(2, 9),
        sender: 'assistant',
        text: "I couldn't retrieve an answer right now. Please verify backend server status.",
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const toggleSources = (msgId: string) => {
    setExpandedSources((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  };

  return (
    <div className="space-y-6 flex flex-col h-[calc(100vh-8rem)]">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            <span>AI Document Assistant</span>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-semibold border border-blue-200">
              FAISS RAG Powered
            </span>
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Ask natural language questions grounded strictly on ingested enterprise documents.
          </p>
        </div>

        {/* Filter by Document */}
        <div className="flex items-center gap-2">
          <label className="text-xs font-semibold text-slate-500 whitespace-nowrap">Focus Document:</label>
          <select
            value={selectedDocId}
            onChange={(e) => setSelectedDocId(e.target.value)}
            className="px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-700 focus:outline-none focus:border-blue-500 max-w-xs shadow-2xs"
          >
            <option value="">All Documents (Global Search)</option>
            {documents.map((d) => (
              <option key={d.document_id} value={d.document_id}>
                {d.document_id} - {d.filename}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Chat Container */}
      <div className="flex-1 bg-white rounded-2xl border border-slate-200/80 shadow-xs flex flex-col overflow-hidden">
        {/* Messages List */}
        <div className="flex-1 p-6 overflow-y-auto space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex gap-3 max-w-3xl ${msg.sender === 'user' ? 'ml-auto flex-row-reverse' : 'mr-auto'}`}
            >
              <div
                className={`w-8 h-8 rounded-xl flex items-center justify-center shrink-0 text-xs font-bold shadow-xs ${
                  msg.sender === 'user' ? 'bg-slate-900 text-white' : 'bg-blue-600 text-white'
                }`}
              >
                {msg.sender === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
              </div>

              <div className="space-y-2">
                <div
                  className={`p-4 rounded-2xl text-xs leading-relaxed ${
                    msg.sender === 'user'
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-600/20'
                      : 'bg-slate-50 border border-slate-200/80 text-slate-800'
                  }`}
                >
                  <div className="whitespace-pre-wrap font-medium">{msg.text}</div>
                  <div
                    className={`text-[10px] mt-2 font-mono ${
                      msg.sender === 'user' ? 'text-blue-200' : 'text-slate-400'
                    }`}
                  >
                    {msg.timestamp}
                  </div>
                </div>

                {/* Grounded Source Citations */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="bg-slate-100/70 border border-slate-200/70 rounded-xl p-3 text-xs">
                    <button
                      onClick={() => toggleSources(msg.id)}
                      className="w-full flex items-center justify-between text-[11px] font-bold text-slate-700 hover:text-blue-600 transition-colors"
                    >
                      <span className="flex items-center gap-1.5">
                        <FileText className="w-3.5 h-3.5 text-blue-600" />
                        Grounded Sources ({msg.sources.length} document chunks)
                      </span>
                      {expandedSources[msg.id] ? (
                        <ChevronUp className="w-3.5 h-3.5" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>

                    {expandedSources[msg.id] && (
                      <div className="mt-2.5 space-y-2 pt-2 border-t border-slate-200">
                        {msg.sources.map((src, sIdx) => (
                          <div key={sIdx} className="p-2 bg-white rounded-lg border border-slate-200/80">
                            <div className="flex items-center justify-between font-mono text-[10px] text-blue-600 font-bold">
                              <span>
                                {src.document_id} • {src.document_type}
                              </span>
                              <span className="text-slate-400 font-sans">
                                Similarity: {(src.score * 100).toFixed(1)}%
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-600 mt-1 italic leading-tight">
                              "{src.snippet}"
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex gap-3 max-w-3xl mr-auto">
              <div className="w-8 h-8 rounded-xl bg-blue-600 text-white flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4" />
              </div>
              <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200/80 flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce" />
                <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce delay-100" />
                <div className="w-2 h-2 rounded-full bg-blue-600 animate-bounce delay-200" />
                <span className="text-xs text-slate-500 font-medium ml-1">
                  Querying FAISS vector index & synthesizing context...
                </span>
              </div>
            </div>
          )}

          <div ref={chatBottomRef} />
        </div>

        {/* Suggestion Chips */}
        <div className="px-6 py-2.5 bg-slate-50/70 border-t border-slate-200 flex items-center gap-2 overflow-x-auto">
          <span className="text-[10px] font-bold uppercase text-slate-400 shrink-0">
            Suggested Prompts:
          </span>
          {SAMPLE_QUESTIONS.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleSendMessage(q)}
              disabled={loading}
              className="px-2.5 py-1 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg text-[11px] font-medium text-slate-700 whitespace-nowrap transition-colors shadow-2xs"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <div className="p-4 border-t border-slate-200 bg-white">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-center gap-2"
          >
            <input
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              placeholder={
                selectedDocId
                  ? `Ask a question about ${selectedDocId}...`
                  : 'Ask any question about your indexed documents...'
              }
              className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-blue-500 focus:bg-white transition-all"
            />
            <button
              type="submit"
              disabled={!inputQuery.trim() || loading}
              className="p-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl shadow-md shadow-blue-600/20 transition-all disabled:opacity-50"
              title="Send Message"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};
