from django import forms
from outsourcing.models import User, JenisJasa, Task, SupervisorPerusahaan, RoleChoices, Perusahaan, GenderChoices


class PasswordMixin:
    def clean(self):
        cleaned_data = super().clean()
        pw  = cleaned_data.get('password')
        cpw = cleaned_data.get('konfirmasi_password')
        if pw and cpw and pw != cpw:
            raise forms.ValidationError('Password dan konfirmasi password tidak cocok.')
        return cleaned_data


# ============================================================
# CREATE FORMS
# ============================================================

class CreateKepalaSupervisorForm(PasswordMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password',
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Konfirmasi Password',
    )
    jenis_jasa = forms.ModelMultipleChoiceField(
        queryset=JenisJasa.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Jenis Jasa yang Ditangani',
    )

    class Meta:
        model  = User
        fields = ['username', 'nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'username'    : forms.TextInput(attrs={'class': 'form-control'}),
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'         : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username'    : 'Username',
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'         : 'NIK / ID Karyawan',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }


class CreateSupervisorForm(PasswordMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password',
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Konfirmasi Password',
    )

    class Meta:
        model  = User
        fields = ['username', 'nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'username'    : forms.TextInput(attrs={'class': 'form-control'}),
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'         : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username'    : 'Username',
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'         : 'NIK / ID Karyawan',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }


class CreateStaffForm(PasswordMixin, forms.ModelForm):
    """
    Supervisor membuat akun Staff.
    Field tasks di-filter sesuai jenis jasa wilayah supervisor,
    lalu diproses di view via StaffTask.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password',
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Konfirmasi Password',
    )
    tasks = forms.ModelMultipleChoiceField(
        queryset=Task.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Skill / Task yang Bisa Dikerjakan',
    )

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if supervisor:
            # Hanya tampilkan task sesuai jenis jasa yang ditugaskan ke supervisor
            jenis_jasa_ids = SupervisorPerusahaan.objects.filter(
                supervisor=supervisor,
                is_active=True,
            ).values_list('jenis_jasa_id', flat=True)
            self.fields['tasks'].queryset = Task.objects.filter(
                jenis_jasa_id__in=jenis_jasa_ids,
                is_active=True,
            ).select_related('jenis_jasa')
        else:
            self.fields['tasks'].queryset = Task.objects.filter(is_active=True)

    class Meta:
        model  = User
        fields = ['username', 'nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'username'    : forms.TextInput(attrs={'class': 'form-control'}),
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'         : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username'    : 'Username',
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'         : 'NIK / ID Karyawan',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }


class CreateCustomerForm(PasswordMixin, forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password',
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Konfirmasi Password',
    )

    class Meta:
        model  = User
        fields = ['username', 'nama_lengkap', 'jenis_kelamin', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'username'    : forms.TextInput(attrs={'class': 'form-control'}),
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username'    : 'Username',
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }


class CreateCustomerSupervisorForm(PasswordMixin, forms.ModelForm):
    """
    Supervisor membuat akun Customer untuk perusahaan yang dia tangani.
    Customer langsung di-link ke perusahaan yang dipilih.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password',
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Konfirmasi Password',
    )
    perusahaan = forms.ModelChoiceField(
        queryset=None,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='Perusahaan',
    )

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if supervisor:
            # Hanya tampilkan perusahaan yang ditugaskan ke supervisor
            perusahaan_ids = SupervisorPerusahaan.objects.filter(
                supervisor=supervisor,
                is_active=True,
            ).values_list('perusahaan_id', flat=True)
            self.fields['perusahaan'].queryset = Perusahaan.objects.filter(
                pk__in=perusahaan_ids,
                is_active=True,
            )

    class Meta:
        model  = User
        fields = ['username', 'nama_lengkap', 'jenis_kelamin', 'telepon', 'foto_profil']
        widgets = {
            'username'    : forms.TextInput(attrs={'class': 'form-control'}),
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'username'    : 'Username',
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
        }


# ============================================================
# EDIT FORMS — per role
# ============================================================

class EditKepalaSupervisorForm(forms.ModelForm):
    jenis_jasa = forms.ModelMultipleChoiceField(
        queryset=JenisJasa.objects.filter(is_active=True),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Jenis Jasa yang Ditangani',
    )

    class Meta:
        model  = User
        fields = ['nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'         : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'         : 'NIK / ID Karyawan',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['jenis_jasa'].initial = (
                self.instance.jasa_yang_dipegang
                    .values_list('jenis_jasa_id', flat=True)
            )


class EditSupervisorForm(forms.ModelForm):
    """Edit Supervisor oleh Kepala Supervisor."""

    password_baru = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Kosongkan jika tidak ingin mengubah',
            'id': 'id_password_baru',
        }),
        label='Password Baru',
        required=False,
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ulangi password baru',
            'id': 'id_konfirmasi_password',
        }),
        label='Konfirmasi Password Baru',
        required=False,
    )

    class Meta:
        model  = User
        fields = ['nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'nama_lengkap' : forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'          : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'      : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nama_lengkap' : 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'          : 'NIK / ID Karyawan',
            'telepon'      : 'Telepon',
            'foto_profil'  : 'Foto Profil',
            'is_active'    : 'Aktif',
        }

        def clean(self):
            cleaned_data = super().clean()
            pw1 = cleaned_data.get('password_baru')
            pw2 = cleaned_data.get('konfirmasi_password')
            # ← hanya cek kalau salah satu diisi
            if pw1 or pw2:
                if pw1 != pw2:
                    raise forms.ValidationError('Password baru dan konfirmasi tidak cocok.')
            return cleaned_data


    def save(self, commit=True):
        user = super().save(commit=False)
        pw = self.cleaned_data.get('password_baru')
        if pw:
            user.set_password(pw)
        if commit:
            user.save()
        return user


class EditStaffForm(forms.ModelForm):
    """
    Edit Staff oleh Supervisor.
    Bisa update tasks (skill) staff, di-filter sesuai wilayah supervisor.
    Password opsional — biarkan kosong jika tidak ingin mengubah.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password Baru',
        required=False,
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Konfirmasi Password Baru',
        required=False,
    )
    tasks = forms.ModelMultipleChoiceField(
        queryset=Task.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Skill / Task yang Bisa Dikerjakan',
    )

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        if supervisor:
            jenis_jasa_ids = SupervisorPerusahaan.objects.filter(
                supervisor=supervisor,
                is_active=True,
            ).values_list('jenis_jasa_id', flat=True)
            self.fields['tasks'].queryset = Task.objects.filter(
                jenis_jasa_id__in=jenis_jasa_ids,
                is_active=True,
            ).select_related('jenis_jasa')
        else:
            self.fields['tasks'].queryset = Task.objects.filter(is_active=True)

        # Pre-select tasks yang sudah dimiliki staff
        if self.instance and self.instance.pk:
            self.fields['tasks'].initial = (
                self.instance.tasks_saya
                    .filter(is_active=True)
                    .values_list('task_id', flat=True)
            )

    class Meta:
        model  = User
        fields = ['nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'         : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'         : 'NIK / ID Karyawan',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }

    def clean(self):
        cleaned_data = super().clean()
        password     = cleaned_data.get('password')
        konfirmasi   = cleaned_data.get('konfirmasi_password')
        if password and konfirmasi and password != konfirmasi:
            raise forms.ValidationError('Password dan konfirmasi password tidak cocok.')
        return cleaned_data


class EditCustomerForm(forms.ModelForm):
    """Edit Customer oleh Admin."""

    class Meta:
        model  = User
        fields = ['nama_lengkap', 'jenis_kelamin', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }


class EditProfilForm(forms.ModelForm):
    """Edit profil diri sendiri — semua role. Tanpa is_active."""

    class Meta:
        model  = User
        fields = ['nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil']
        widgets = {
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'         : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'         : 'NIK / ID Karyawan',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
        }


# ============================================================
# GANTI PASSWORD — semua role
# ============================================================

class GantiPasswordForm(forms.Form):
    password_lama = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password Lama',
    )
    password_baru = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password Baru',
    )
    konfirmasi_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Konfirmasi Password Baru',
    )

    def clean(self):
        cleaned_data = super().clean()
        pw  = cleaned_data.get('password_baru')
        cpw = cleaned_data.get('konfirmasi_password')
        if pw and cpw and pw != cpw:
            raise forms.ValidationError('Password baru dan konfirmasi tidak cocok.')
        return cleaned_data


# ============================================================
# GENERIC EDIT FORM — untuk Admin
# ============================================================

class EditUserForm(forms.ModelForm):
    """Form edit user generik untuk Admin — basic fields saja."""

    class Meta:
        model  = User
        fields = ['nama_lengkap', 'jenis_kelamin', 'nik', 'telepon', 'foto_profil', 'is_active']
        widgets = {
            'nama_lengkap': forms.TextInput(attrs={'class': 'form-control'}),
            'jenis_kelamin': forms.Select(attrs={'class': 'form-control'}),
            'nik'         : forms.TextInput(attrs={'class': 'form-control'}),
            'telepon'     : forms.TextInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'nama_lengkap': 'Nama Lengkap',
            'jenis_kelamin': 'Jenis Kelamin',
            'nik'         : 'NIK / ID Karyawan',
            'telepon'     : 'Telepon',
            'foto_profil' : 'Foto Profil',
            'is_active'    : 'Aktif',
        }