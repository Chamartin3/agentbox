import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/api/http', () => ({
  apiRequest: vi.fn(),
}));
import { apiRequest } from '@/api/http';
import RunRatingStars from '@/components/runs/RunRatingStars';

const req = apiRequest as unknown as ReturnType<typeof vi.fn>;

describe('RunRatingStars', () => {
  beforeEach(() => {
    req.mockReset();
  });

  it('renders 5 stars', () => {
    render(<RunRatingStars runId="r1" initialRating={null} />);
    expect(screen.getAllByRole('button')).toHaveLength(5);
  });

  it('fills stars up to the initial rating', () => {
    const { container } = render(<RunRatingStars runId="r1" initialRating={3} />);
    const filled = container.querySelectorAll('.star.filled');
    const empty = container.querySelectorAll('.star.empty');
    expect(filled).toHaveLength(3);
    expect(empty).toHaveLength(2);
  });

  it('clicking a star posts the rating', async () => {
    const user = userEvent.setup();
    req.mockResolvedValue({ rating: 4 });
    const onChange = vi.fn();
    render(<RunRatingStars runId="r1" initialRating={null} onRatingChange={onChange} />);

    await user.click(screen.getByLabelText('Rate 4 stars'));

    await waitFor(() => expect(req).toHaveBeenCalled());
    expect(req).toHaveBeenCalledWith(
      '/api/runs/r1/rating',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ rating: 4 }) }),
    );
    expect(onChange).toHaveBeenCalledWith(4);
  });

  it('clicking the current rating clears it', async () => {
    const user = userEvent.setup();
    req.mockResolvedValue(undefined);
    const onChange = vi.fn();
    render(<RunRatingStars runId="r1" initialRating={3} onRatingChange={onChange} />);

    await user.click(screen.getByLabelText('Rate 3 stars'));

    await waitFor(() => expect(req).toHaveBeenCalled());
    expect(req).toHaveBeenCalledWith(
      '/api/runs/r1/rating',
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('readOnly disables buttons and skips the request', async () => {
    const user = userEvent.setup();
    render(<RunRatingStars runId="r1" initialRating={2} readOnly />);
    const buttons = screen.getAllByRole('button');
    buttons.forEach((b) => expect((b as HTMLButtonElement).disabled).toBe(true));
    await user.click(buttons[0]);
    expect(req).not.toHaveBeenCalled();
  });
});
