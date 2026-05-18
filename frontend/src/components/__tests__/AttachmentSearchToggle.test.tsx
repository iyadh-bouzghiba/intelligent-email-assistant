import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AttachmentSearchToggle from '../AttachmentSearchToggle';

const defaultProps = {
  isActive: false,
  label: 'Has attachment',
  isRTL: false,
  disabled: false,
  onToggle: vi.fn(),
};

describe('AttachmentSearchToggle', () => {
  it('renders with correct role and aria-checked when inactive', () => {
    render(<AttachmentSearchToggle {...defaultProps} />);
    const btn = screen.getByRole('switch');
    expect(btn).toHaveAttribute('aria-checked', 'false');
  });

  it('renders with aria-checked true when active', () => {
    render(<AttachmentSearchToggle {...defaultProps} isActive={true} />);
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  });

  it('calls onToggle when enabled and clicked', () => {
    const onToggle = vi.fn();
    render(<AttachmentSearchToggle {...defaultProps} onToggle={onToggle} />);
    fireEvent.click(screen.getByRole('switch'));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('does not call onToggle when disabled', () => {
    const onToggle = vi.fn();
    render(<AttachmentSearchToggle {...defaultProps} disabled={true} onToggle={onToggle} />);
    fireEvent.click(screen.getByRole('switch'));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('displays the label text', () => {
    render(<AttachmentSearchToggle {...defaultProps} label="Filter attachments" />);
    expect(screen.getByText('Filter attachments')).toBeInTheDocument();
  });

  it('applies flex-row-reverse class when isRTL is true', () => {
    render(<AttachmentSearchToggle {...defaultProps} isRTL={true} />);
    expect(screen.getByRole('switch')).toHaveClass('flex-row-reverse');
  });

  it('does not apply flex-row-reverse class when isRTL is false', () => {
    render(<AttachmentSearchToggle {...defaultProps} isRTL={false} />);
    expect(screen.getByRole('switch')).not.toHaveClass('flex-row-reverse');
  });
});
