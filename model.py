
# %%
import pytorch_lightning as pl
from pytorch_lightning.metrics.functional.classification import auroc
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.optim.lr_scheduler import OneCycleLR
import timm


# TODO:
# Implementere FixRes?
# scheduler
# hvorfor tager jeg torch.max??
# Logge val_loss så jeg kan bruge overfit_batches??
# der er vidst noget galt med val_auc eller med min model. Første epoch er værre en random??
# for et par epochs freeze feature extraction.
# Derefter køre med stigende lr fra tail to head.


# def on_epoch_start(self):
#     if self.current_epoch == 0:
#         self.freeze()
#         self.trainer.lr_schedulers = ... # Define new scheduler

#     if self.current_epoch == N_FREEZE_EPOCHS:
#         self.unfreeze() # Or partially unfreeze
#         self.trainer.lr_schedulers = ... # Define new scheduler

nn.BatchNorm2d(3)
# %%


class MRKnee(pl.LightningModule):
    def __init__(self, model_name='efficientnet_b1',
                 learning_rate=0.001,
                 total_steps=None):
        super().__init__()
        self.learning_rate = learning_rate
        self.total_steps = total_steps
        # layers
        self.bn_ax = nn.BatchNorm2d(3)
        self.model_ax = timm.create_model(
            model_name, pretrained=True, num_classes=0)
        self.bn_sag = nn.BatchNorm2d(3)
        self.model_sag = timm.create_model(
            model_name, pretrained=True, num_classes=0)
        self.bn_cor = nn.BatchNorm2d(3)
        self.model_cor = timm.create_model(
            model_name, pretrained=True, num_classes=0)  # set global_pool='' to return unpooled

        self.clf = nn.Linear(1280*3, 1)

    def run_model(self, model, bn, series):
        x = torch.squeeze(series, dim=0)
        x = bn(x)
        x = model(x)
        x = torch.max(x, 0, keepdim=True)[0]  # Hvad gør det?
        return x

    def forward(self, x):
        ax, sag, cor = x
        ax = self.run_model(self.model_ax, self.bn_ax, ax)
        sag = self.run_model(self.model_sag, self.bn_sag, sag)
        cor = self.run_model(self.model_cor, self.bn_cor, cor)
        y = torch.cat((ax, sag, cor), 1)
        return self.clf(y)

    def training_step(self, batch, batchidx):
        imgs, label, sample_id, weight = batch
        logit = self(imgs)
        loss = F.binary_cross_entropy_with_logits(
            logit, label, pos_weight=weight)
        self.log('train_loss', loss, prog_bar=True)
        return loss

    def validation_step(self, batch, batchidx):
        imgs, label, sample_id, weight = batch
        logit = self(imgs)
        loss = F.binary_cross_entropy_with_logits(
            logit, label, pos_weight=weight)

        self.preds.append(torch.sigmoid(logit).item())
        self.lbl.append(label.item())
        self.log('val_loss', loss, prog_bar=True)
        return loss

    def configure_optimizers(self):
        optimizer = torch.optim.Adam(self.parameters(), lr=0.001, weight_decay=.01)
        scheduler = OneCycleLR(optimizer, max_lr=self.learning_rate,
                               total_steps=self.total_steps)
        return [optimizer], [scheduler]

    def on_validation_epoch_start(self):
        self.preds = []
        self.lbl = []

    def on_validation_epoch_end(self):
        self.log('val_auc', auroc(torch.Tensor(
            self.preds), torch.Tensor(self.lbl), pos_label=1), prog_bar=True)

# %%
