interface Props {
  kind: 'ok' | 'error';
  msg: string;
}
export default function Toast({ kind, msg }: Props) {
  return <div className={`toast ${kind}`}>{msg}</div>;
}
