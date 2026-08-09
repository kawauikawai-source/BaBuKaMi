(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  B.runtimeConfig = Object.assign({}, B.runtimeConfig || {}, {
    apiBaseUrl: '/api'
  });
})(window);
