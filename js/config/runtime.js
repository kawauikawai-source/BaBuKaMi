(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  B.runtimeConfig = Object.assign({
    apiBaseUrl: ''
  }, B.runtimeConfig || {});
})(window);
