module.exports = {
  createChart: jest.fn(() => ({
    addCandlestickSeries: jest.fn(() => ({ setData: jest.fn() })),
    addHistogramSeries: jest.fn(() => ({ setData: jest.fn() })),
    applyOptions: jest.fn(),
    timeScale: jest.fn(() => ({ fitContent: jest.fn() })),
    priceScale: jest.fn(() => ({ applyOptions: jest.fn() })),
    remove: jest.fn(),
    resize: jest.fn(),
  })),
};
