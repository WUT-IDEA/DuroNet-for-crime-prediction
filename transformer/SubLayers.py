''' Define the sublayers in encoder/decoder layer '''
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from transformer.Modules import ScaledDotProductAttention
from transformer.tcn import TemporalConvNet, SpatialTemporalConvNet


class MultiHeadAttention(nn.Module):
    ''' Multi-Head Attention module '''

    def __init__(self, n_head, d_model, d_k, d_v, dropout=0.1, seq_len=15, kernel = 'linear', kernel_size_tcn = 3, kernel_size_scn = 2):  #kernel:'linear', 'tcn', 'stcn'
        super().__init__()

        self.n_head = n_head
        self.d_k = d_k
        self.d_v = d_v
        self.kernel = kernel

        self.w_qs = nn.Linear(d_model, n_head * d_k, bias=False)
        self.fc = nn.Linear(n_head * d_v, d_model, bias=False)
        kernel_layers = 1

        if kernel == 'tcn':
            self.w_ks = TemporalConvNet(d_model, [n_head * d_k]*kernel_layers, kernel_size=3, dropout=0.2)
            self.w_vs = TemporalConvNet(d_model, [n_head * d_v]*kernel_layers, kernel_size=3, dropout=0.2)
        elif kernel == 'stcn':
            self.w_ks = SpatialTemporalConvNet(seq_len, d_model, [n_head * d_k]*kernel_layers, kernel_size_tcn=kernel_size_tcn, kernel_size_scn = kernel_size_scn, dropout=0.2)
            self.w_vs = SpatialTemporalConvNet(seq_len, d_model, [n_head * d_v]*kernel_layers, kernel_size_tcn=kernel_size_tcn, kernel_size_scn = kernel_size_scn, dropout=0.2)
        elif kernel == 'linear':
            self.w_ks = nn.Linear(d_model, n_head * d_k, bias=False)
            self.w_vs = nn.Linear(d_model, n_head * d_v, bias=False)

        self.attention = ScaledDotProductAttention(temperature=d_k ** 0.5)

        self.dropout = nn.Dropout(dropout)
        self.layer_norm = nn.LayerNorm(d_model, eps=1e-6)


    def forward(self, q, k, v, mask=None, tcn=True):

        d_k, d_v, n_head = self.d_k, self.d_v, self.n_head
        sz_b, len_q, len_k, len_v = q.size(0), q.size(1), k.size(1), v.size(1)

        residual = q
        q = self.layer_norm(q)

        # Pass through the pre-attention projection: b x lq x (n*dv)
        # Separate different heads: b x lq x n x dv
        q = self.w_qs(q).view(sz_b, len_q, n_head, d_k)
        if self.kernel == 'linear':
            k = self.w_ks(k).view(sz_b, len_k, n_head, d_k)
            v = self.w_vs(v).view(sz_b, len_v, n_head, d_v)
        else:
            k, v = k.transpose(1, 2), v.transpose(1, 2)
            k = self.w_ks(k).transpose(1, 2).view(sz_b, len_k, n_head, d_k)
            v = self.w_vs(v).transpose(1, 2).view(sz_b, len_v, n_head, d_v)

        # Transpose for attention dot product: b x n x lq x dv
        q, k, v = q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2)
        
        if mask is not None:
            mask = mask.unsqueeze(1)   # For head axis broadcasting.

        output, attn = self.attention(q, k, v, mask=mask)

        # Transpose to move the head dimension back: b x lq x n x dv
        # Combine the last two dimensions to concatenate all the heads together: b x lq x (n*dv)
        output = output.transpose(1, 2).contiguous().view(sz_b, len_q, -1)
        output = self.dropout(self.fc(output))
        output += residual

        return output, attn


class PositionwiseFeedForward(nn.Module):
    ''' A two-feed-forward-layer module '''

    def __init__(self, d_in, d_hid, dropout=0.1):
        super().__init__()
        self.w_1 = nn.Linear(d_in, d_hid) # position-wise
        self.w_2 = nn.Linear(d_hid, d_in) # position-wise
        self.layer_norm = nn.LayerNorm(d_in, eps=1e-6)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        residual = x
        x = self.layer_norm(x)
        output = self.w_2(F.relu(self.w_1(x)))
        output = self.dropout(output)
        output += residual
        return output
