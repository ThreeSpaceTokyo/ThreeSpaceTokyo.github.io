---
layout: single
title: "Mendtokyo — Thank you"
author_profile: false
permalink: /mendtokyo/thanks/
sitemap: false
toc: false
classes: wide
---

{% include mendtokyo/style.html %}

<div class="mending" markdown="0">
<div data-lang="en">
  <h2>Thank you — your seat is booked.</h2>
  <p class="lead">Square has emailed you a receipt. Here is what happens next:</p>
  <ul>
    <li><strong>When &amp; where:</strong> <span class="when"></span> at Three Space Tokyo, 3-6-6 Asakusabashi, Taito-ku, Tokyo — about 6 minutes on foot from Asakusabashi Station (JR Sobu / Toei Asakusa line, exit A4). Please arrive 5–10 minutes early.</li>
    <li><strong>What to bring:</strong> nothing is required; aprons, arm covers and gloves are provided. Wear clothes you don’t mind getting a spot of lacquer on, and bring your glasses if you use them for close-up work.</li>
    <li><strong>Changes:</strong> free cancellation up to 24 hours before the session; after that the seat is non-refundable but transferable. Email <a href="mailto:threespacetokyo@gmail.com">threespacetokyo@gmail.com</a>.</li>
  </ul>
  <p><a class="btn-line" href="/mendtokyo/">Back to the workshop page</a></p>
</div>
<div data-lang="fr" hidden>
  <h2>Merci — votre place est réservée.</h2>
  <p class="lead">Square vous a envoyé un reçu par e-mail. La suite :</p>
  <ul>
    <li><strong>Quand et où :</strong> <span class="when"></span> à Three Space Tokyo, 3-6-6 Asakusabashi, Taito-ku, Tokyo — à environ 6 minutes à pied de la gare d’Asakusabashi (JR Sobu / Toei Asakusa, sortie A4). Merci d’arriver 5 à 10 minutes en avance.</li>
    <li><strong>À apporter :</strong> rien n’est nécessaire ; tabliers, manchettes et gants sont fournis. Portez des vêtements qui ne craignent pas une tache de laque et apportez vos lunettes si vous en utilisez pour le travail de près.</li>
    <li><strong>Modifications :</strong> annulation gratuite jusqu’à 24 h avant ; ensuite la place n’est pas remboursable mais peut être cédée. Écrivez à <a href="mailto:threespacetokyo@gmail.com">threespacetokyo@gmail.com</a>.</li>
  </ul>
  <p><a class="btn-line" href="/mendtokyo/fr/">Retour à la page de l’atelier</a></p>
</div>
<div data-lang="ja" hidden>
  <h2>ご予約ありがとうございます。</h2>
  <p class="lead">Squareより領収書メールをお送りしました。当日について：</p>
  <ul>
    <li><strong>日時・会場：</strong> <span class="when"></span>、Three Space Tokyo（東京都台東区浅草橋3-6-6）。浅草橋駅（JR総武線・都営浅草線、A4出口）から徒歩約6分。開始5〜10分前にお越しください。</li>
    <li><strong>持ち物：</strong> 特にありません。エプロン・アームカバー・手袋はご用意します。漆が付いても気にならない服装で、手元用の眼鏡をお使いの方はお持ちください。</li>
    <li><strong>変更・キャンセル：</strong> 開始24時間前まで無料。それ以降の返金はできませんが、他の方への譲渡は可能です。<a href="mailto:threespacetokyo@gmail.com">threespacetokyo@gmail.com</a> までご連絡ください。</li>
  </ul>
  <p><a class="btn-line" href="/mendtokyo/ja/">ワークショップのページへ戻る</a></p>
</div>
<div data-lang="vi" hidden>
  <h2>Cảm ơn bạn — chỗ của bạn đã được đặt.</h2>
  <p class="lead">Square đã gửi biên lai qua email. Tiếp theo:</p>
  <ul>
    <li><strong>Thời gian &amp; địa điểm:</strong> <span class="when"></span> tại Three Space Tokyo, 3-6-6 Asakusabashi, Taito-ku, Tokyo — khoảng 6 phút đi bộ từ ga Asakusabashi (JR Sobu / Toei Asakusa, lối ra A4). Vui lòng đến sớm 5–10 phút.</li>
    <li><strong>Mang theo:</strong> không cần gì; tạp dề, ống tay và găng tay có sẵn. Mặc đồ không ngại dính sơn và mang kính nếu bạn dùng kính để nhìn gần.</li>
    <li><strong>Thay đổi:</strong> hủy miễn phí đến 24 giờ trước buổi học; sau đó không hoàn tiền nhưng có thể chuyển cho người khác. Email <a href="mailto:threespacetokyo@gmail.com">threespacetokyo@gmail.com</a>.</li>
  </ul>
  <p><a class="btn-line" href="/mendtokyo/vi/">Quay lại trang workshop</a></p>
</div>
<script>
(function(){
  var q = new URLSearchParams(location.search), lang = q.get("lang") || "en";
  if (!document.querySelector('[data-lang="'+lang+'"]')) lang = "en";
  document.querySelectorAll("[data-lang]").forEach(function(el){ el.hidden = el.getAttribute("data-lang") !== lang; });
  var d = q.get("d"), t = q.get("t") || "";
  if (d) {
    var dt = new Date(d + "T00:00:00+09:00");
    var loc = {en:"en-GB", fr:"fr-FR", ja:"ja-JP", vi:"vi-VN"}[lang];
    var txt = dt.toLocaleDateString(loc, {weekday:"short", day:"numeric", month:"short", year:"numeric", timeZone:"Asia/Tokyo"}) + (t ? " · " + t : "");
    document.querySelectorAll(".when").forEach(function(el){ el.textContent = txt; });
  }
})();
</script>
</div>
