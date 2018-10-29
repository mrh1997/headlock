Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/cosmic64"
  config.vm.provision "shell", inline: <<-SHELL
    apt install -y libclang1-7
  SHELL
end
