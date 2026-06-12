import { useRef, type KeyboardEvent, type WheelEvent } from 'react';

export interface CategoryPillBarProps {
    categories: string[];
    activeCategoryCode: string;
    onSelect: (code: string) => void;
    getLabel: (code: string) => string;
    isRTL: boolean;
    ariaLabel: string;
}

const CategoryPillBar = ({
    categories,
    activeCategoryCode,
    onSelect,
    getLabel,
    isRTL,
    ariaLabel,
}: CategoryPillBarProps) => {
    const buttonRefs = useRef<Array<HTMLButtonElement | null>>([]);

    const moveSelection = (targetIndex: number) => {
        if (categories.length === 0) return;

        const safeIndex = Math.max(0, Math.min(targetIndex, categories.length - 1));
        const nextCode = categories[safeIndex];

        buttonRefs.current[safeIndex]?.focus();

        if (nextCode !== activeCategoryCode) {
            onSelect(nextCode);
        }
    };

    const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
        if (categories.length === 0) return;

        const previousKey = isRTL ? 'ArrowRight' : 'ArrowLeft';
        const nextKey = isRTL ? 'ArrowLeft' : 'ArrowRight';

        switch (event.key) {
            case previousKey:
            case nextKey: {
                event.preventDefault();
                const delta = event.key === nextKey ? 1 : -1;
                const nextIndex = (index + delta + categories.length) % categories.length;
                moveSelection(nextIndex);
                return;
            }
            case 'Home':
                event.preventDefault();
                moveSelection(0);
                return;
            case 'End':
                event.preventDefault();
                moveSelection(categories.length - 1);
                return;
            case ' ':
            case 'Enter':
                event.preventDefault();
                onSelect(categories[index]);
                return;
            default:
                return;
        }
    };

    const handlePillWheel = (e: WheelEvent<HTMLDivElement>) => {
        if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
        e.preventDefault();
        e.currentTarget.scrollLeft += e.deltaY;
    };

    return (
        <div className="w-full">
            <div
                role="radiogroup"
                aria-label={ariaLabel}
                dir={isRTL ? 'rtl' : 'ltr'}
                onWheel={handlePillWheel}
                className="flex items-stretch gap-2 overflow-x-auto whitespace-nowrap pb-1 [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden"
            >
                {categories.map((code, index) => {
                    const isActive = code === activeCategoryCode;

                    return (
                        <button
                            key={code}
                            ref={(node) => {
                                buttonRefs.current[index] = node;
                            }}
                            type="button"
                            role="radio"
                            aria-checked={isActive}
                            tabIndex={isActive ? 0 : -1}
                            onClick={() => onSelect(code)}
                            onKeyDown={(event) => handleKeyDown(event, index)}
                            className={[
                                'min-h-11 shrink-0 rounded-2xl border px-4 py-2.5 text-[11px] font-black uppercase tracking-[0.18em] transition-all focus:outline-none focus:ring-2 focus:ring-primary-500/60 focus:ring-offset-0',
                                isActive
                                    ? 'border-primary-500/70 bg-primary-600 text-white shadow-lg shadow-primary-600/20'
                                    : 'border-white/10 bg-white/[0.03] text-slate-400 hover:border-white/20 hover:text-slate-200',
                            ].join(' ')}
                        >
                            {getLabel(code)}
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

export default CategoryPillBar;
