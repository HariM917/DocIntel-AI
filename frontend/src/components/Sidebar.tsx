import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  FileUp,
  FolderArchive,
  ShieldCheck,
  BotMessageSquare,
  LogOut,
  Sparkles,
  Shield,
  FileText,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';

export const Sidebar: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const navItems = [
    { label: 'Dashboard', path: '/', icon: LayoutDashboard },
    { label: 'Process Document', path: '/process', icon: FileUp, highlight: true },
    { label: 'Document Archive', path: '/archive', icon: FolderArchive },
    { label: 'Security Rules', path: '/security', icon: ShieldCheck },
    { label: 'AI Assistant', path: '/assistant', icon: BotMessageSquare },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col justify-between shrink-0 select-none text-slate-300">
      {/* Brand Header */}
      <div>
        <div className="h-16 flex items-center px-6 gap-3 border-b border-slate-800/80 bg-slate-950/40">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/20 text-white font-bold">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <div className="font-bold text-base tracking-tight text-white flex items-center gap-1.5">
              DOCINTEL <span className="text-xs px-1.5 py-0.5 rounded-md bg-blue-500/20 text-blue-400 font-semibold border border-blue-500/30">AI</span>
            </div>
            <div className="text-[10px] text-slate-400 uppercase tracking-wider font-medium">Enterprise Intelligence</div>
          </div>
        </div>

        {/* Navigation Section */}
        <div className="px-3 py-6">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 px-3 mb-2">
            Main Platform
          </div>
          <nav className="space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  className={({ isActive }) =>
                    `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                      isActive
                        ? 'bg-blue-600 text-white shadow-md shadow-blue-600/30'
                        : 'text-slate-400 hover:text-white hover:bg-slate-800/60'
                    }`
                  }
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                  {item.highlight && (
                    <span className="ml-auto w-2 h-2 rounded-full bg-emerald-400 shadow-sm shadow-emerald-400/50 animate-pulse" />
                  )}
                </NavLink>
              );
            })}
          </nav>

          {/* AI Status Badge */}
          <div className="mt-8 mx-1 p-3.5 rounded-xl bg-gradient-to-b from-slate-800/80 to-slate-900 border border-slate-800 shadow-sm">
            <div className="flex items-center gap-2 text-xs font-semibold text-white mb-1.5">
              <Sparkles className="w-3.5 h-3.5 text-blue-400" />
              <span>Intelligence Active</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              RoBERTa NER, PII Masking & FAISS Vector RAG Engine running in memory.
            </p>
          </div>
        </div>
      </div>

      {/* User Footer */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/30">
        <div className="flex items-center justify-between p-2 rounded-xl bg-slate-800/40 border border-slate-700/40">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-blue-500 text-white font-bold flex items-center justify-center text-xs shadow-inner">
              {user?.full_name ? user.full_name[0].toUpperCase() : 'U'}
            </div>
            <div className="min-w-0">
              <div className="text-xs font-medium text-white truncate">
                {user?.full_name || 'Administrator'}
              </div>
              <div className="text-[10px] text-slate-400 truncate">
                {user?.email || 'admin@docintel.ai'}
              </div>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="Log Out"
            className="p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition-colors"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
};
