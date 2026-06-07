/* ぽぽちゃんの Live2D 描画とリップシンク制御。
 * pixi.js + pixi-live2d-display(cubism4) を使い、ParamMouthOpenY を外部から駆動できるようにする。
 */
(function () {
  "use strict";

  const MODEL_URL = "/models/hiyori/Hiyori.model3.json";
  const MOUTH_PARAM = "ParamMouthOpenY"; // model3.json の LipSync グループより

  let app = null;
  let model = null;
  let mouthOverride = -1; // -1: 上書きしない / 0..1: 口の開き

  function fit() {
    if (!model || !app) return;
    // app.screen は論理(CSS)サイズ。renderer.width は物理(×devicePixelRatio)なので、
    // Retina(dpr=2)で使うと x=w/2 が画面右端になり、キャラが右に寄る（要 app.screen）。
    const w = app.screen.width;
    const h = app.screen.height;
    const scale = (h * 0.92) / model.internalModel.originalHeight;
    model.scale.set(scale);
    model.x = w / 2;
    model.y = h * 0.5;
  }

  async function init(canvas) {
    if (!window.PIXI || !window.PIXI.live2d) {
      throw new Error("PIXI / pixi-live2d-display が読み込まれていません");
    }
    app = new PIXI.Application({
      view: canvas,
      resizeTo: canvas.parentElement,
      backgroundAlpha: 0,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });

    model = await PIXI.live2d.Live2DModel.from(MODEL_URL, { autoInteract: false });
    model.anchor.set(0.5, 0.5);
    app.stage.addChild(model);
    fit();
    app.renderer.on("resize", fit);

    // 口パク: 内部 update の後に ParamMouthOpenY を上書きする（モーション適用後）
    const im = model.internalModel;
    const baseUpdate = im.update.bind(im);
    im.update = function () {
      baseUpdate.apply(im, arguments);
      if (mouthOverride >= 0) {
        im.coreModel.setParameterValueById(MOUTH_PARAM, mouthOverride);
      }
    };

    return model;
  }

  // value: 0..1（-1 で口の制御を待機モーションに戻す）
  function setMouth(value) {
    mouthOverride = value;
  }

  window.Popo = { init, setMouth };
})();
