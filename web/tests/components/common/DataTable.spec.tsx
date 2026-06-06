import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataTable, { ColumnDef } from '@/components/common/DataTable';

interface Row {
  id: string;
  name: string;
  size: number;
}

const ROWS: Row[] = [
  { id: 'a', name: 'alpha', size: 3 },
  { id: 'b', name: 'beta', size: 1 },
  { id: 'c', name: 'gamma', size: 2 },
];

const COLS: ColumnDef<Row>[] = [
  { key: 'name', header: 'Name', accessor: (r) => r.name, sortable: true, searchable: true },
  { key: 'size', header: 'Size', accessor: (r) => r.size, sortable: true, align: 'right' },
];

describe('DataTable (client mode)', () => {
  it('renders all rows', () => {
    render(<DataTable<Row> columns={COLS} rowKey={(r) => r.id} data={ROWS} />);
    expect(screen.getByText('alpha')).not.toBeNull();
    expect(screen.getByText('beta')).not.toBeNull();
    expect(screen.getByText('gamma')).not.toBeNull();
  });

  it('shows empty message when data is empty', () => {
    render(
      <DataTable<Row>
        columns={COLS}
        rowKey={(r) => r.id}
        data={[]}
        emptyMessage="nothing here"
      />,
    );
    expect(screen.getByText('nothing here')).not.toBeNull();
  });

  it('filters rows by the search box', async () => {
    const user = userEvent.setup();
    render(<DataTable<Row> columns={COLS} rowKey={(r) => r.id} data={ROWS} />);
    await user.type(screen.getByPlaceholderText('search…'), 'beta');
    // wait past the internal debounce
    await new Promise((r) => setTimeout(r, 400));
    expect(screen.queryByText('alpha')).toBeNull();
    expect(screen.getByText('beta')).not.toBeNull();
  });

  it('clicking a sortable header toggles the order indicator', async () => {
    const user = userEvent.setup();
    render(<DataTable<Row> columns={COLS} rowKey={(r) => r.id} data={ROWS} />);
    const header = screen.getByRole('columnheader', { name: /Size/ });
    await user.click(header);
    expect(header.textContent).toMatch(/▲|▼/);
  });
});
