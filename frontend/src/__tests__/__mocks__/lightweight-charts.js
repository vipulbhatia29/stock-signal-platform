module.exports = {
  createChart: jest.fn(() => ({
    addSeries: jest.fn(() => ({ setData: jest.fn() })),
    applyOptions: jest.fn(),
    timeScale: jest.fn(() => ({ fitContent: jest.fn() })),
    priceScale: jest.fn(() => ({ applyOptions: jest.fn() })),
    remove: jest.fn(),
    resize: jest.fn(),
  })),
  CandlestickSeries: Symbol("CandlestickSeries"),
  HistogramSeries: Symbol("HistogramSeries"),
};
