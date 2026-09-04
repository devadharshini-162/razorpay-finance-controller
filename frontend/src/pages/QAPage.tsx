import React, { useState } from 'react';
import { Send, Bot, User, Sparkles, ShieldCheck, ChevronDown, ChevronUp } from 'lucide-react';
import type { QAMessage } from '../types';
import { askQuestionApi } from '../services/api';

interface QAPageProps {
  sessionId: string;
}

export const QAPage: React.FC<QAPageProps> = ({ sessionId }) => {
  const [messages, setMessages] = useState<QAMessage[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      text: 'Hello! I am your Grounded Finance Assistant. Ask me any question regarding your reconciled settlement dataset, fee deductions, unmatched records, or specific UTRs.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [expandedMessageId, setExpandedMessageId] = useState<string | null>(null);

  const sampleQuestions = [
    'How many transactions were matched?',
    'What is the total settled amount?',
    'How much was deducted in fees and GST?',
    'Show unresolved records',
  ];

  const handleSend = async (questionText: string) => {
    const q = questionText.trim();
    if (!q || loading) return;

    const userMsg: QAMessage = {
      id: `u-${Date.now()}`,
      sender: 'user',
      text: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res = await askQuestionApi(sessionId, q);
      const assistantMsg: QAMessage = {
        id: `a-${Date.now()}`,
        sender: 'assistant',
        text: res.answer,
        evidence: res.evidence,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err: any) {
      const errorMsg: QAMessage = {
        id: `err-${Date.now()}`,
        sender: 'assistant',
        text: `Error: ${err.message || 'Could not answer question.'}`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-140px)] flex-col rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xs overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 p-4 bg-slate-50/70 dark:bg-slate-800/40">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Grounded Settlement Q&A
              </h2>
              <span className="flex items-center gap-1 rounded-full bg-emerald-50 dark:bg-emerald-950/60 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                <ShieldCheck className="h-3 w-3" />
                Fact-Checked Grounding
              </span>
            </div>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              Answers are computed strictly from deterministic facts without hallucination.
            </p>
          </div>
        </div>
      </div>

      {/* Messages Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex items-start gap-3 ${
              msg.sender === 'user' ? 'flex-row-reverse' : ''
            }`}
          >
            <div
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl ${
                msg.sender === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300'
              }`}
            >
              {msg.sender === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
            </div>

            <div
              className={`max-w-2xl rounded-2xl p-4 text-xs leading-relaxed ${
                msg.sender === 'user'
                  ? 'bg-blue-600 text-white shadow-md'
                  : 'border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-white shadow-xs'
              }`}
            >
              <p className="font-medium whitespace-pre-wrap">{msg.text}</p>

              {/* Collapsible Evidence Section for Assistant Messages */}
              {msg.evidence && (
                <div className="mt-3 border-t border-slate-200 dark:border-slate-700/60 pt-2.5">
                  <button
                    onClick={() =>
                      setExpandedMessageId(expandedMessageId === msg.id ? null : msg.id)
                    }
                    className="flex items-center gap-1.5 text-[11px] font-semibold text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    <span>Verified Facts & Evidence</span>
                    {expandedMessageId === msg.id ? (
                      <ChevronUp className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5" />
                    )}
                  </button>

                  {expandedMessageId === msg.id && (
                    <div className="mt-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-3 text-[11px] text-slate-700 dark:text-slate-300 space-y-1.5">
                      {msg.evidence.record_ids && (
                        <p><span className="font-semibold">Records:</span> {msg.evidence.record_ids.length ? msg.evidence.record_ids.join(', ') : 'None'}</p>
                      )}
                      {msg.evidence.facts && Object.entries(msg.evidence.facts).map(([key, value]) => (
                        <p key={key}><span className="font-semibold capitalize">{key.replace(/_/g, ' ')}:</span> {Array.isArray(value) ? (value.length ? value.join(', ') : 'None') : String(value)}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <span
                className={`mt-1.5 block text-[10px] ${
                  msg.sender === 'user' ? 'text-blue-200' : 'text-slate-400'
                }`}
              >
                {msg.timestamp}
              </span>
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex items-center gap-2 text-xs text-slate-400 italic font-medium">
            <Sparkles className="h-4 w-4 animate-spin text-blue-500" />
            <span>Computing grounded answer from settlement facts...</span>
          </div>
        )}
      </div>

      {/* Suggested Question Pills */}
      <div className="border-t border-slate-200 dark:border-slate-800 p-3 bg-slate-50/50 dark:bg-slate-900/50">
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <span className="text-[11px] font-bold text-slate-400 shrink-0">Try Asking:</span>
          {sampleQuestions.map((sq) => (
            <button
              key={sq}
              onClick={() => handleSend(sq)}
              disabled={loading}
              className="shrink-0 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-800 px-3 py-1 text-[11px] font-medium text-slate-700 dark:text-slate-300 hover:border-blue-500 hover:text-blue-600 transition-all disabled:opacity-50"
            >
              {sq}
            </button>
          ))}
        </div>
      </div>

      {/* Input Box */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend(input);
        }}
        className="flex items-center gap-2 border-t border-slate-200 dark:border-slate-800 p-3 bg-white dark:bg-slate-900"
      >
        <input
          type="text"
          placeholder="Ask a question about fees, settled amounts, or UTRs..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={loading}
          className="flex-1 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/50 px-4 py-2.5 text-xs text-slate-900 dark:text-white focus:border-blue-500 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 transition-all shadow-md"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
};
