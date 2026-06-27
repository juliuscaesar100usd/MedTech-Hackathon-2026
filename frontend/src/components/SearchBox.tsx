import { useState, type FormEvent } from 'react';

export function SearchBox({
  initial = '',
  placeholder = 'Поиск…',
  buttonLabel = 'Найти',
  hero = false,
  autoFocus = false,
  onSearch,
}: {
  initial?: string;
  placeholder?: string;
  buttonLabel?: string;
  hero?: boolean;
  autoFocus?: boolean;
  onSearch: (value: string) => void;
}) {
  const [value, setValue] = useState(initial);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSearch(value.trim());
  }

  return (
    <form className={`searchbox${hero ? ' hero' : ''}`} onSubmit={handleSubmit} role="search">
      <input
        className="input"
        type="search"
        value={value}
        placeholder={placeholder}
        autoFocus={autoFocus}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Поисковый запрос"
      />
      <button className="btn btn-primary" type="submit">
        {buttonLabel}
      </button>
    </form>
  );
}
