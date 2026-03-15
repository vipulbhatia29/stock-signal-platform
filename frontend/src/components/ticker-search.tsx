"use client";

import { useState, useEffect, useRef } from "react";
import { useStockSearch } from "@/hooks/use-stocks";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { SearchIcon, PlusCircleIcon } from "lucide-react";

// Tickers are 1-5 uppercase alphanumeric chars (covers US equities + ETFs like BRK.B)
const TICKER_RE = /^[A-Za-z0-9.]{1,6}$/;

interface TickerSearchProps {
  onSelect: (ticker: string) => void;
}

export function TickerSearch({ onSelect }: TickerSearchProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null);

  useEffect(() => {
    timerRef.current = setTimeout(() => setDebouncedQuery(query), 300);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [query]);

  const { data: results, isLoading } = useStockSearch(debouncedQuery);

  function handleSelect(ticker: string) {
    onSelect(ticker);
    setOpen(false);
    setQuery("");
    setDebouncedQuery("");
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={
        <Button
          variant="outline"
          className="w-full max-w-md justify-start gap-2 text-muted-foreground font-normal"
        >
          <SearchIcon className="size-4" />
          Search stocks to add...
        </Button>
      } />
      <PopoverContent className="w-80 p-0 bg-card2 border-border" align="start">
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="Search by ticker or name..."
            value={query}
            onValueChange={setQuery}
          />
          <CommandList>
            {isLoading && debouncedQuery && (
              <div className="py-4 text-center text-sm text-subtle">
                Searching...
              </div>
            )}
            {!isLoading && debouncedQuery && (!results || results.length === 0) && (
              <CommandEmpty>No stocks found</CommandEmpty>
            )}
            {results && results.length > 0 && (
              <CommandGroup>
                {results.map((stock) => (
                  <CommandItem
                    key={stock.ticker}
                    value={stock.ticker}
                    onSelect={() => handleSelect(stock.ticker)}
                    className="hover:bg-hov text-foreground"
                  >
                    <div className="flex flex-1 items-center justify-between">
                      <div>
                        <span className="font-mono font-semibold">
                          {stock.ticker}
                        </span>
                        <span className="ml-2 text-muted-foreground">
                          {stock.name}
                        </span>
                      </div>
                      {stock.sector && (
                        <span className="text-xs text-muted-foreground">
                          {stock.sector}
                        </span>
                      )}
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {/* Open-world: allow adding any valid ticker not yet in DB */}
            {!isLoading &&
              debouncedQuery &&
              TICKER_RE.test(debouncedQuery) &&
              !results?.some(
                (s) => s.ticker === debouncedQuery.toUpperCase()
              ) && (
                <CommandGroup heading="Add new ticker">
                  <CommandItem
                    value={`add-${debouncedQuery}`}
                    onSelect={() => handleSelect(debouncedQuery.toUpperCase())}
                    className="hover:bg-hov text-foreground"
                  >
                    <PlusCircleIcon className="mr-2 size-4 text-muted-foreground" />
                    <span>
                      Add{" "}
                      <span className="font-mono font-semibold">
                        {debouncedQuery.toUpperCase()}
                      </span>
                    </span>
                  </CommandItem>
                </CommandGroup>
              )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
