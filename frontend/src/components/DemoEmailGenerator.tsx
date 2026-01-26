import { motion } from 'framer-motion';
import { Mail, Sparkles } from 'lucide-react';

interface DemoEmailGeneratorProps {
    onGenerate: (emailData: { subject: string; sender: string; body: string }) => void;
    loading?: boolean;
}

const DEMO_EMAILS = [
    {
        title: "Project Deadline",
        subject: "Urgent: Project Alpha Deadline Extension",
        sender: "client@example.com",
        body: `Hi Team,

We're seeing some delays on our end with the design review process. The stakeholders need an extra two days to finalize their feedback.

Can we push the Project Alpha deadline from Friday to next Monday? This would give us enough time to incorporate all changes properly.

Let me know if this works for your schedule.

Best regards,
Sarah`
    },
    {
        title: "Meeting Request",
        subject: "Q1 Planning Meeting - Scheduling",
        sender: "manager@company.com",
        body: `Hello everyone,

I'd like to schedule our Q1 planning meeting for next week. We need to discuss:

1. Budget allocation for new initiatives
2. Team expansion plans
3. Technology stack decisions
4. Client onboarding process improvements

Please let me know your availability for Tuesday or Wednesday afternoon.

Thanks,
Michael`
    },
    {
        title: "Feature Request",
        subject: "New Feature: Email Analytics Dashboard",
        sender: "product@startup.io",
        body: `Hey dev team,

Our users have been requesting an analytics dashboard to track their email engagement metrics. This would include:

- Open rates
- Response times
- Thread resolution rates
- Peak activity hours

This is becoming a top priority for our enterprise clients. Can we discuss feasibility and timeline in tomorrow's standup?

Cheers,
Alex`
    }
];

export function DemoEmailGenerator({ onGenerate, loading }: DemoEmailGeneratorProps) {
    return (
        <div className="space-y-6">
            <div className="text-center space-y-2">
                <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary-500/10 border border-primary-500/20 text-primary-400 text-xs font-bold uppercase tracking-widest">
                    <Sparkles size={12} />
                    <span>Quick Demo</span>
                </div>
                <h3 className="text-xl font-bold text-white">Try Example Emails</h3>
                <p className="text-slate-400 text-sm">
                    Click any example to instantly analyze it
                </p>
            </div>

            <div className="grid md:grid-cols-3 gap-4">
                {DEMO_EMAILS.map((email, index) => (
                    <motion.button
                        key={index}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.1 }}
                        onClick={() => onGenerate(email)}
                        disabled={loading}
                        className="glass-card p-6 text-left space-y-3 hover:border-primary-500/30 transition-all group disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        <div className="flex items-start gap-3">
                            <div className="w-10 h-10 rounded-lg bg-primary-500/10 flex items-center justify-center text-primary-500 group-hover:bg-primary-500 group-hover:text-white transition-all">
                                <Mail size={20} />
                            </div>
                            <div className="flex-1 min-w-0">
                                <h4 className="font-semibold text-white text-sm mb-1 group-hover:text-primary-400 transition-colors">
                                    {email.title}
                                </h4>
                                <p className="text-xs text-slate-500 truncate">
                                    {email.subject}
                                </p>
                            </div>
                        </div>
                        <p className="text-xs text-slate-400 line-clamp-3 leading-relaxed">
                            {email.body.substring(0, 100)}...
                        </p>
                    </motion.button>
                ))}
            </div>
        </div>
    );
}
